import argparse
import io
import os
import requests
import sys
import time
import urllib

from voussoirkit import bytestring
from voussoirkit import dotdict
from voussoirkit import httperrors
from voussoirkit import pathclass
from voussoirkit import pipeable
from voussoirkit import progressbars
from voussoirkit import ratelimiter
from voussoirkit import sentinel
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'downloady')

USERAGENT = '''
'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)
Chrome/42.0.2311.152 Safari/537.36'
'''.strip().replace('\n', ' ')

HEADERS = {
    'User-Agent': USERAGENT,
}

FILENAME_BADCHARS = '*?"<>|\r\n'

# When using dynamic chunk sizing, this is the ideal time to process a
# single chunk, in seconds.
IDEAL_CHUNK_TIME = 0.2

TIMEOUT = 60
TEMP_EXTENSION = '.downloadytemp'

if os.name == 'nt':
    SPECIAL_FILENAMES = pathclass.WINDOWS_RESERVED_NAMES
else:
    SPECIAL_FILENAMES = [os.devnull]
SPECIAL_FILENAMES = [os.path.normcase(x) for x in SPECIAL_FILENAMES]

FILE_EXISTS = sentinel.Sentinel('file exists no overwrite', truthyness=False)

class DownloadyException(Exception):
    pass

class NotEnoughBytes(DownloadyException):
    pass

class ServerNoRange(DownloadyException):
    pass

class SpecialPath:
    '''
    This class is to be used for special paths like /dev/null and Windows's nul.
    Unlike regular download paths, these special paths will not be renamed with
    a temporary file extension, and the containing paths will not be checked
    for existence or mkdir'ed.
    '''
    def __init__(self, path):
        self.absolute_path = path

    def open(self, *args, **kwargs):
        return open(self.absolute_path, *args, **kwargs)

def download_file(
        url,
        localname=None,
        auth=None,
        bytespersecond=None,
        progressbar=None,
        do_head=True,
        headers=None,
        overwrite=False,
        raise_for_undersized=True,
        ratemeter=None,
        timeout=None,
        verbose=False,
        verify_ssl=True,
    ):
    plan = prepare_plan(
        url,
        localname,
        auth=auth,
        bytespersecond=bytespersecond,
        progressbar=progressbar,
        do_head=do_head,
        headers=headers,
        overwrite=overwrite,
        raise_for_undersized=raise_for_undersized,
        ratemeter=ratemeter,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )

    if isinstance(plan, sentinel.Sentinel):
        return plan

    return download_plan(plan)

def download_plan(plan):
    if isinstance(plan.download_into, pathclass.Path):
        plan.download_into.parent.makedirs(exist_ok=True)
        plan.download_into.touch()

    if plan.plan_type in ['resume', 'partial']:
        if isinstance(plan.download_into, io.IOBase):
            file_handle = plan.download_into
            if plan.seek_to > 0:
                file_handle.seek(plan.seek_to)
        else:
            file_handle = plan.download_into.open('r+b')
            file_handle.seek(plan.seek_to)
        bytes_downloaded = plan.seek_to

    elif plan.plan_type == 'fulldownload':
        if isinstance(plan.download_into, io.IOBase):
            file_handle = plan.download_into
        else:
            file_handle = plan.download_into.open('wb')
        bytes_downloaded = 0

    if plan.header_range_min is not None:
        plan.headers['range'] = 'bytes={min}-{max}'.format(
            min=plan.header_range_min,
            max=plan.header_range_max,
        )

    log.info('Downloading %s into "%s"', plan.url, plan.real_localname)

    download_stream = request(
        'get',
        plan.url,
        stream=True,
        auth=plan.auth,
        headers=plan.headers,
        timeout=plan.timeout,
        verify_ssl=plan.verify_ssl,
    )

    if plan.remote_total_bytes is None:
        # Since we didn't do a head, let's fill this in now.
        plan.remote_total_bytes = int(download_stream.headers.get('Content-Length', None))

    progressbar = progressbars.normalize_progressbar(plan.progressbar, total=plan.remote_total_bytes)

    if plan.limiter:
        chunk_size = int(plan.limiter.allowance * IDEAL_CHUNK_TIME)
    else:
        chunk_size = 128 * bytestring.KIBIBYTE

    while True:
        chunk_start = time.perf_counter()
        chunk = download_stream.raw.read(chunk_size)
        chunk_bytes = len(chunk)
        if chunk_bytes == 0:
            break

        file_handle.write(chunk)
        bytes_downloaded += chunk_bytes

        if progressbar is not None:
            progressbar.step(bytes_downloaded)

        if plan.limiter is not None:
            plan.limiter.limit(chunk_bytes)

        if plan.ratemeter is not None:
            plan.ratemeter.digest(chunk_bytes)

        chunk_time = time.perf_counter() - chunk_start
        chunk_size = dynamic_chunk_sizer(chunk_size, chunk_time, IDEAL_CHUNK_TIME)

    if progressbar is not None:
        progressbar.done()

    # Don't close the user's file handle
    if isinstance(plan.real_localname, io.IOBase):
        return plan.real_localname

    file_handle.close()

    # Don't try to rename /dev/null or other special names
    if isinstance(plan.real_localname, SpecialPath):
        return plan.real_localname

    temp_localsize = plan.download_into.size
    undersized = (
        plan.plan_type != 'partial' and
        plan.remote_total_bytes is not None and
        temp_localsize < plan.remote_total_bytes
    )
    if undersized and plan.raise_for_undersized:
        message = 'File does not contain expected number of bytes. Received {size} / {total}'
        message = message.format(size=temp_localsize, total=plan.remote_total_bytes)
        raise NotEnoughBytes(message)

    if plan.download_into != plan.real_localname:
        os.rename(plan.download_into, plan.real_localname)

    return plan.real_localname

def dynamic_chunk_sizer(chunk_size, chunk_time, ideal_chunk_time):
    '''
    Calculates a new chunk size based on the time it took to do the previous
    chunk versus the ideal chunk time.
    '''
    # If chunk_time = scale * ideal_chunk_time,
    # Then ideal_chunk_size = chunk_size / scale
    scale = chunk_time / ideal_chunk_time
    scale = min(scale, 2)
    scale = max(scale, 0.5)
    suggestion = chunk_size / scale
    # Give the current size double weight so small fluctuations don't send
    # the needle bouncing all over.
    new_size = int((chunk_size + chunk_size + suggestion) / 3)
    # I doubt any real-world scenario will dynamically suggest a chunk_size of
    # zero, but let's enforce a one-byte minimum anyway.
    new_size = max(new_size, 1)
    return new_size

def prepare_plan(
        url,
        localname,
        auth=None,
        bytespersecond=None,
        progressbar=None,
        do_head=True,
        headers=None,
        overwrite=False,
        raise_for_undersized=True,
        ratemeter=None,
        timeout=TIMEOUT,
        verify_ssl=True,
    ):
    # Chapter 1: File existence
    headers = headers or {}
    user_provided_range = 'range' in headers

    url = sanitize_url(url)
    if localname in [None, '']:
        localname = basename_from_url(url)

    if isinstance(localname, io.IOBase):
        real_localname = localname
        temp_localname = localname
        real_exists = False
        temp_exists = False
    elif is_special_file(localname):
        real_localname = SpecialPath(localname)
        temp_localname = SpecialPath(localname)
        real_exists = False
        temp_exists = False
    else:
        localname = pathclass.Path(localname)
        if localname.is_dir:
            localname = localname.with_child(basename_from_url(url))
        localname = sanitize_filename(localname.absolute_path)
        real_localname = pathclass.Path(localname)
        temp_localname = real_localname.add_extension(TEMP_EXTENSION)
        real_exists = real_localname.exists
        temp_exists = temp_localname.exists

    if real_exists and overwrite is False and not user_provided_range:
        log.debug('File exists and overwrite is off. Nothing to do.')
        return FILE_EXISTS

    if isinstance(real_localname, SpecialPath):
        temp_localsize = 0
    elif isinstance(real_localname, io.IOBase):
        try:
            temp_localsize = real_localname.tell()
        except io.UnsupportedOperation:
            temp_localsize = 0
    else:
        temp_localsize = int(temp_exists and temp_localname.size)

    # Chapter 2: Ratelimiting
    if bytespersecond is None:
        limiter = None
    elif isinstance(bytespersecond, ratelimiter.Ratelimiter):
        limiter = bytespersecond
    else:
        limiter = ratelimiter.Ratelimiter(allowance=bytespersecond)

    # Chapter 3: Extracting range
    if user_provided_range:
        user_range_min = int(headers['range'].split('bytes=')[1].split('-')[0])
        user_range_max = headers['range'].split('-')[1]
        if user_range_max != '':
            user_range_max = int(user_range_max)
    else:
        user_range_min = None
        user_range_max = None

    # Chapter 4: Server range support
    # Always include a range on the first request to figure out whether the
    # server supports it. Use 0- to get correct remote_total_bytes
    if user_provided_range and not do_head:
        raise DownloadyException('Cannot determine range support without the head request')

    temp_headers = headers.copy()
    temp_headers.update({'range': 'bytes=0-'})

    if do_head:
        # I'm using a GET instead of an actual HEAD here because some servers respond
        # differently, even though they're not supposed to.
        head = request('get', url, stream=True, headers=temp_headers, auth=auth)
        remote_total_bytes = int(head.headers.get('content-length', None))
        server_respects_range = (head.status_code == 206 and 'content-range' in head.headers)
        head.connection.close()
    else:
        remote_total_bytes = None
        server_respects_range = False

    if user_provided_range and not server_respects_range:
        raise ServerNoRange('Server did not respect your range header')

    # Chapter 5: Plan definitions
    plan_base = {
        'url': url,
        'auth': auth,
        'progressbar': progressbar,
        'limiter': limiter,
        'headers': headers,
        'real_localname': real_localname,
        'raise_for_undersized': raise_for_undersized,
        'ratemeter': ratemeter,
        'remote_total_bytes': remote_total_bytes,
        'timeout': timeout,
        'verify_ssl': verify_ssl,
    }
    plan_fulldownload = dotdict.DotDict(
        plan_base,
        download_into=temp_localname,
        header_range_min=None,
        header_range_max=None,
        plan_type='fulldownload',
        seek_to=0,
    )
    plan_resume = dotdict.DotDict(
        plan_base,
        download_into=temp_localname,
        header_range_min=temp_localsize,
        header_range_max='',
        plan_type='resume',
        seek_to=temp_localsize,
    )
    plan_partial = dotdict.DotDict(
        plan_base,
        download_into=real_localname,
        header_range_min=user_range_min,
        header_range_max=user_range_max,
        plan_type='partial',
        seek_to=user_range_min,
    )

    # Chapter 6: Redeem your meal vouchers here
    if real_exists:
        if overwrite:
            os.remove(real_localname)

        if user_provided_range:
            return plan_partial

        return plan_fulldownload

    elif temp_exists and temp_localsize > 0:
        if overwrite:
            return plan_fulldownload

        if user_provided_range:
            return plan_partial

        if server_respects_range:
            log.info('Resume from byte %d' % plan_resume.seek_to)
            return plan_resume

    else:
        if user_provided_range:
            return plan_partial

        return plan_fulldownload

    raise DownloadyException('No plan was chosen?')

def basename_from_url(url):
    '''
    Determine the local filename appropriate for a URL.
    '''
    localname = urllib.parse.unquote(url)
    localname = localname.rstrip('/')
    localname = localname.split('?')[0]
    localname = localname.rsplit('/', 1)[-1]
    return localname

def is_special_file(file):
    if isinstance(file, pathclass.Path):
        return False
    file = os.path.normpath(file)
    file = file.rsplit(os.sep)[-1]
    file = os.path.normcase(file)
    return file in SPECIAL_FILENAMES

def request(method, url, headers=None, timeout=TIMEOUT, verify_ssl=True, **kwargs):
    if headers is None:
        headers = {}
    else:
        headers = headers.copy()

    for (key, value) in HEADERS.items():
        headers.setdefault(key, value)

    session = requests.Session()
    a = requests.adapters.HTTPAdapter(max_retries=30)
    b = requests.adapters.HTTPAdapter(max_retries=30)
    session.mount('http://', a)
    session.mount('https://', b)
    session.max_redirects = 40

    method = {
        'get': session.get,
        'head': session.head,
        'post': session.post,
    }[method]

    response = method(url, headers=headers, timeout=timeout, verify=verify_ssl, **kwargs)
    httperrors.raise_for_status(response)
    return response

def sanitize_filename(text, exclusions=''):
    to_remove = FILENAME_BADCHARS
    for exclude in exclusions:
        to_remove = to_remove.replace(exclude, '')

    for char in to_remove:
        text = text.replace(char, '')

    (drive, path) = os.path.splitdrive(text)
    path = path.replace(':', '')
    text = drive + path

    return text

def sanitize_url(url):
    url = url.replace('%3A//', '://')
    return url

def download_argparse(args):
    url = pipeable.input(args.url, split_lines=False)

    if args.progressbar.lower() in {'none', 'off'}:
        progressbar = None
    if args.progressbar.lower() == 'bar':
        progressbar = progressbars.bar1_bytestring

    bytespersecond = args.bytespersecond
    if bytespersecond is not None:
        bytespersecond = bytestring.parsebytes(bytespersecond)

    headers = {}
    if args.range is not None:
        headers['range'] = 'bytes=%s' % args.range

    retry = args.retry
    if not retry:
        retry = 1

    while retry != 0:
        # Negative numbers permit infinite retries.
        try:
            download_file(
                url=url,
                localname=args.localname,
                bytespersecond=bytespersecond,
                progressbar=progressbar,
                do_head=args.no_head is False,
                headers=headers,
                overwrite=args.overwrite,
                timeout=args.timeout,
                verbose=True,
                verify_ssl=args.no_ssl is False,
            )
        except (NotEnoughBytes, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
            retry -= 1
            if retry == 0:
                raise
        else:
            break

@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('url')
    parser.add_argument('localname', nargs='?', default=None)
    parser.add_argument('--progressbar', default='bar')
    parser.add_argument('-bps', '--bytespersecond', dest='bytespersecond', default=None)
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--range', default=None)
    parser.add_argument('--timeout', type=int, default=TIMEOUT)
    parser.add_argument('--retry', nargs='?', type=int, default=1)
    parser.add_argument('--no_head', '--no-head', dest='no_head', action='store_true')
    parser.add_argument('--no_ssl', '--no-ssl', dest='no_ssl', action='store_true')
    parser.set_defaults(func=download_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
