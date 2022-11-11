'''
This module provides functions related to walking the filesystem and
copying files and folders.
'''
import collections
import hashlib
import os
import shutil
import time

from voussoirkit import bytestring
from voussoirkit import dotdict
from voussoirkit import pathclass
from voussoirkit import progressbars
from voussoirkit import ratelimiter
from voussoirkit import sentinel
from voussoirkit import vlogging
from voussoirkit import winglob

log = vlogging.getLogger(__name__)

BAIL = sentinel.Sentinel('BAIL')
YIELD_STYLE_FLAT = sentinel.Sentinel('yield style flat')
YIELD_STYLE_NESTED = sentinel.Sentinel('yield style nested')

OVERWRITE_ALL = sentinel.Sentinel('overwrite all files')
OVERWRITE_OLD = sentinel.Sentinel('overwrite old files')

# Number of bytes to read and write at a time
CHUNK_SIZE = 2 * bytestring.MIBIBYTE

# When using dynamic chunk sizing, this is the ideal time to process a
# single chunk, in seconds.
IDEAL_CHUNK_TIME = 0.2

HASH_CLASS = hashlib.md5

class SpinalException(Exception):
    pass

class DestinationIsDirectory(SpinalException):
    pass

class DestinationIsFile(SpinalException):
    pass

class HashVerificationFailed(SpinalException):
    pass

class RecursiveDirectory(SpinalException):
    pass

class SourceNotDirectory(SpinalException):
    pass

class SourceNotFile(SpinalException):
    pass

class SpinalError(SpinalException):
    pass

def copy_directory(
        source,
        destination=None,
        *,
        bytes_per_second=None,
        callback_permission_denied=None,
        callback_post_file=None,
        callback_pre_directory=None,
        callback_pre_file=None,
        chunk_size='dynamic',
        destination_new_root=None,
        directory_progressbar=None,
        dry_run=False,
        exclude_directories=None,
        exclude_filenames=None,
        file_progressbar=None,
        files_per_second=None,
        hash_class=None,
        overwrite=OVERWRITE_OLD,
        precalcsize=False,
        skip_symlinks=True,
        stop_event=None,
        verify_hash=False,
        verify_hash_progressbar=None,
    ):
    '''
    Copy all of the contents from source to destination,
    including subdirectories.

    source:
        The directory which will be copied.

    destination:
        The directory in which copied files are placed. Alternatively, use
        destination_new_root.

    bytes_per_second:
        Passed into each `copy_file` as `bytes_per_second`.

    callback_permission_denied:
        Passed into `walk` and each `copy_file` as `callback_permission_denied`.

    callback_pre_directory:
        This function will be called before each directory and subdirectory
        begins copying their files. It will be called with three arguments:
        source directory, destination directory, dry_run.
        This function may return the BAIL sentinel (return spinal.BAIL) and
        that directory will be skipped.
        Note: BAIL will only skip a single directory. If you wish to terminate
        the entire copy procedure, use `stop_event` which will finish copying
        the current file and then stop.

    callback_pre_file:
        Passed into each `copy_file` as `callback_pre_copy`.

    callback_post_file:
        This function will be called after the file finishes copying with one
        argument: the dotdict returned by copy_file.
        If you think copy_dir should be rewritten as a generator instead,
        I agree!

    chunk_size:
        Passed into each `copy_file` as `chunk_size`.

    destination_new_root:
        Determine the destination path by calling
        `new_root(source, destination_new_root)`.
        Thus, this path acts as a root and the rest of the path is matched.

        `destination` and `destination_new_root` are mutually exclusive.

    directory_progressbar:
        An instance of voussoirkit.progressbars.ProgressBar.
        This progressbar will be updated after each file copy with the number of
        bytes written into the destination directory so far. If `precalcsize` is
        True, the progressbar will have its total set to that value. Otherwise
        it will be indeterminate.

    dry_run:
        Do everything except the actual file copying.

    exclude_filenames:
        Passed directly into `walk`.

    exclude_directories:
        Passed directly into `walk`.

    files_per_second:
        Maximum number of files to be processed per second. Helps to keep CPU
        usage low.

    file_progressbar:
        Passed into each `copy_file` as `progressbar`.

    hash_class:
        Passed into each `copy_file` as `hash_class`.

    overwrite:
        Passed into each `copy_file` as `overwrite`.

    precalcsize:
        If True, calculate the size of source before beginning the copy.
        This number can be used in the directory_progressbar.
        This may take a while if the source directory is large.

    skip_symlinks:
        If True, symlink dirs are skipped and symlink files are not copied.

    stop_event:
        If provided, a threading.Event object which when set indicates that we
        should finish the current file and then stop the remainder of the copy.
        For example, you can run this function in a thread and let the main
        thread catch ctrl+c to set the stop_event, so the copy can stop cleanly.

    verify_hash:
        Passed into each `copy_file` as `verify_hash`.

    verify_hash_progressbar:
        Passed into each `copy_file` as `verify_hash_progressbar`.

    Returns a dotdict containing at least these values:
    `source` pathclass.Path
    `destination` pathclass.Path
    `written_files` int, number of files that were written
    `written_bytes` int, number of bytes that were written
    '''
    # Prepare parameters
    if not is_xor(destination, destination_new_root):
        message = 'One and only one of `destination` and '
        message += '`destination_new_root` can be passed.'
        raise ValueError(message)

    source = pathclass.Path(source)
    source.correct_case()

    if destination_new_root is not None:
        destination = new_root(source, destination_new_root)

    destination = pathclass.Path(destination)
    destination.correct_case()

    if destination in source:
        raise RecursiveDirectory(source, destination)

    if not source.is_dir:
        raise SourceNotDirectory(source)

    if destination.is_file:
        raise DestinationIsFile(destination)

    if precalcsize is True:
        total_bytes = get_dir_size(source)
    else:
        total_bytes = 0

    directory_progressbar = progressbars.normalize(
        directory_progressbar,
        topic=destination.absolute_path,
        total=total_bytes if precalcsize else None,
    )
    callback_pre_directory = callback_pre_directory or do_nothing
    callback_pre_file = callback_pre_file or do_nothing
    callback_post_file = callback_post_file or do_nothing
    bytes_per_second = limiter_or_none(bytes_per_second)
    files_per_second = limiter_or_none(files_per_second)

    # Copy
    walker = walk(
        source,
        callback_permission_denied=callback_permission_denied,
        exclude_directories=exclude_directories,
        exclude_filenames=exclude_filenames,
        sort=True,
        yield_style=YIELD_STYLE_NESTED,
    )

    def denester(walker):
        for (directory, children, files) in walker:
            if skip_symlinks and directory.is_link:
                continue
            # The source abspath will only end in os.sep if it is the drive root.
            # Non-root folders already have their trailing slash stripped by
            # pathclass. Using rstrip helps us make the following transformation:
            # source: A:\
            # destination_new_root: B:\backup
            # A:\myfile.txt
            # -> replace(A:, B:\backup\A)
            # -> B:\backup\A\myfile.txt
            #
            # Without disturbing the other case in which source is not drive root.
            # source: A:\Documents
            # destination_new_root: B:\backup\A\Documents
            # A:\Documents\myfile.txt
            # -> replace(A:\Documents, B:\backup\A\Documents)
            # -> B:\backup\A\Documents\myfile.txt
            destination_dir = pathclass.Path(directory.absolute_path.replace(
                source.absolute_path.rstrip(os.sep),
                destination.absolute_path,
                1
            ))

            if callback_pre_directory(directory, destination_dir, dry_run=dry_run) is BAIL:
                continue

            if stop_event and stop_event.is_set():
                break

            for source_file in files:
                destination_file = destination_dir.with_child(source_file.basename)
                yield (source_file, destination_file)

    walker = denester(walker)
    written_files = 0
    written_bytes = 0

    for (source_file, destination_file) in walker:
        if stop_event and stop_event.is_set():
            break

        if skip_symlinks and source_file.is_link:
            continue

        if destination_file.is_dir:
            raise DestinationIsDirectory(destination_file)

        if not dry_run:
            destination_file.parent.makedirs(exist_ok=True)

        copied = copy_file(
            source_file,
            destination_file,
            bytes_per_second=bytes_per_second,
            callback_permission_denied=callback_permission_denied,
            callback_pre_copy=callback_pre_file,
            chunk_size=chunk_size,
            dry_run=dry_run,
            hash_class=hash_class,
            overwrite=overwrite,
            progressbar=file_progressbar,
            verify_hash=verify_hash,
            verify_hash_progressbar=verify_hash_progressbar,
        )

        if copied.written:
            written_files += 1
            written_bytes += copied.written_bytes

        directory_progressbar.step(written_bytes)
        callback_post_file(copied)

        if files_per_second is not None:
            files_per_second.limit(1)

    directory_progressbar.done()

    results = dotdict.DotDict(
        source=source,
        destination=destination,
        written_files=written_files,
        written_bytes=written_bytes,
        default=None,
    )
    return results

# Alias for your convenience.
copy_dir = copy_directory

def copy_file(
        source,
        destination=None,
        *,
        bytes_per_second=None,
        callback_permission_denied=None,
        callback_pre_copy=None,
        chunk_size='dynamic',
        destination_new_root=None,
        dry_run=False,
        hash_class=None,
        overwrite=OVERWRITE_OLD,
        progressbar=None,
        verify_hash=False,
        verify_hash_progressbar=None,
    ):
    '''
    Copy a file from one place to another.

    source:
        The file to copy.

    destination:
        The filename of the new copy. Alternatively, use
        destination_new_root.

    destination_new_root:
        Determine the destination path by calling
        `new_root(source_dir, destination_new_root)`.
        Thus, this path acts as a root and the rest of the path is matched.

    bytes_per_second:
        Restrict file copying to this many bytes per second. Can be an integer,
        an existing Ratelimiter object, or a string parseable by bytestring.
        The bytestring BYTE, KIBIBYTE, etc constants may help.

    callback_permission_denied:
        If provided, this function will be called when a source file denies
        read access, with the exception object as the only argument.
        THE OPERATION WILL RETURN NORMALLY.

        If not provided, the PermissionError is raised.

    callback_pre_copy:
        This function will be called just before the destination filepath is
        created and the handles opened. It will be called with three arguments:
        source file, destination file, dry_run.
        This function may return the BAIL sentinel (return spinal.BAIL) and
        that file will not be copied.

    chunk_size:
        An integer number of bytes to read and write at a time.
        Or, the string 'dynamic' to enable dynamic chunk sizing that aims to
        keep a consistent pace of progress bar updates.

    dry_run:
        Do everything except the actual file copying.

    hash_class:
        If provided, should be a hashlib class or a callable that returns an
        instance of one. The hash will be computed while the file is being
        copied. The instance will be returned in the dotdict as `hash`.
        Note that if the function returns early due to dry_run or file not
        needing overwrite, this won't be set, so be prepared to handle None.
        If None, the hash will not be calculated.

    overwrite:
        This option decides what to do when the destination file already exists.
        If OVERWRITE_ALL, the file will be overwritten.
        If OVERWRITE_OLD, the file will be overwritten if the source file
        has a more recent "last modified" timestamp (i.e. stat.mtime).
        If any other value, the file will not be overwritten. False or None
        would be good values to pass.

    progressbar:
        An instance of voussoirkit.progressbars.ProgressBar.

    verify_hash:
        If True, the copied file will be read back after the copy is complete,
        and its hash will be compared against the hash of the source file.
        If hash_class is None, then the global HASH_CLASS is used.

    verify_hash_progressbar:
        Passed into `hash_file` as `progressbar` when verifying the hash.

    Returns a dotdict containing at least these values:
    `source` pathclass.Path
    `destination` pathclass.Path
    `written` bool, False if file was skipped, True if written
    `written_bytes` int, number of bytes that were written
    '''
    # Prepare parameters
    if not is_xor(destination, destination_new_root):
        message = 'One and only one of `destination` and '
        message += '`destination_new_root` can be passed'
        raise ValueError(message)

    source = pathclass.Path(source)
    source.correct_case()
    source_bytes = source.size

    if not source.is_file:
        raise SourceNotFile(source)

    if destination_new_root is not None:
        destination = new_root(source, destination_new_root)
    destination = pathclass.Path(destination)

    progressbar = progressbars.normalize(
        progressbar,
        topic=destination.absolute_path,
        total=0 if dry_run else source_bytes,
    )
    callback_pre_copy = callback_pre_copy or do_nothing

    if destination.is_dir:
        destination = destination.with_child(source.basename)

    bytes_per_second = limiter_or_none(bytes_per_second)

    results = dotdict.DotDict(
        source=source,
        destination=destination,
        written=False,
        written_bytes=0,
        default=None,
    )

    # I'm putting the overwrite_all test first since an `is` is faster and
    # cheaper than the dest.exists which will invoke a stat check.
    should_overwrite = (
        (overwrite is OVERWRITE_ALL) or
        (not destination.exists) or
        (overwrite is OVERWRITE_OLD and source.stat.st_mtime > destination.stat.st_mtime)
    )

    if not should_overwrite:
        return results

    if dry_run:
        progressbar.done()
        return results

    if callback_pre_copy(source, destination, dry_run=dry_run) is BAIL:
        return results

    destination.parent.makedirs(exist_ok=True)

    def handlehelper(path, mode):
        try:
            handle = path.open(mode)
            return handle
        except PermissionError as exception:
            if callback_permission_denied is not None:
                callback_permission_denied(exception)
                return None
            else:
                raise

    log.loud('Opening source handle.')
    source_handle = handlehelper(source, 'rb')
    log.loud('Opening dest handle.')
    destination_handle = handlehelper(destination, 'wb')

    if source_handle is None and destination_handle:
        destination_handle.close()
        return results

    if destination_handle is None:
        source_handle.close()
        return results

    if hash_class is not None:
        results.hash = hash_class()
    elif verify_hash:
        hash_class = HASH_CLASS
        results.hash = HASH_CLASS()

    dynamic_chunk_size = chunk_size == 'dynamic'
    if dynamic_chunk_size:
        chunk_size = bytestring.MIBIBYTE

    while True:
        chunk_start = time.perf_counter()

        try:
            data_chunk = source_handle.read(chunk_size)
        except PermissionError as exception:
            if callback_permission_denied is not None:
                callback_permission_denied(exception)
                return results
            else:
                raise

        data_bytes = len(data_chunk)
        if data_bytes == 0:
            break

        if results.hash:
            results.hash.update(data_chunk)

        destination_handle.write(data_chunk)
        results.written_bytes += data_bytes

        progressbar.step(results.written_bytes)

        if bytes_per_second is not None:
            bytes_per_second.limit(data_bytes)

        if dynamic_chunk_size:
            chunk_time = time.perf_counter() - chunk_start
            chunk_size = dynamic_chunk_sizer(chunk_size, chunk_time, IDEAL_CHUNK_TIME)

    progressbar.done()

    # Fin
    log.loud('Closing source handle.')
    source_handle.close()
    log.loud('Closing dest handle.')
    destination_handle.close()
    log.debug('Copying metadata.')
    shutil.copystat(source, destination)
    results.written = True

    if verify_hash:
        file_hash = _verify_hash(
            destination,
            progressbar=verify_hash_progressbar,
            hash_class=hash_class,
            known_hash=results.hash.hexdigest(),
            known_size=source_bytes,
        )
        results.verified_hash = file_hash

    return results

def do_nothing(*args, **kwargs):
    '''
    Used by other functions as the default callback. It does nothing!
    '''
    return

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

def get_dir_size(path):
    '''
    Calculate the total number of bytes across all files in this directory
    and its subdirectories.
    '''
    path = pathclass.Path(path)

    if not path.is_dir:
        raise SourceNotDirectory(path)

    total_bytes = 0
    for filepath in walk(path):
        total_bytes += filepath.size

    return total_bytes

def hash_file(
        path,
        hash_class,
        *,
        bytes_per_second=None,
        chunk_size='dynamic',
        progressbar=None,
    ):
    '''
    hash_class:
        Should be a hashlib class or a callable that returns an instance of one.

    bytes_per_second:
        Restrict file hashing to this many bytes per second. Can be an integer,
        an existing Ratelimiter object, or a string parseable by bytestring.
        The bytestring BYTE, KIBIBYTE, etc constants may help.

    chunk_size:
        An integer number of bytes to read at a time.
        Or, the string 'dynamic' to enable dynamic chunk sizing that aims to
        keep a consistent pace of progress bar updates.

    progressbar:
        An instance from voussoirkit.progressbars.
    '''
    path = pathclass.Path(path)
    path.assert_is_file()
    hasher = hash_class()

    bytes_per_second = limiter_or_none(bytes_per_second)
    progressbar = progressbars.normalize(
        progressbar,
        topic=path.absolute_path,
        total=path.size,
    )

    checked_bytes = 0

    handle = path.open('rb')

    dynamic_chunk_size = chunk_size == 'dynamic'
    if dynamic_chunk_size:
        chunk_size = bytestring.MIBIBYTE

    with handle:
        while True:
            chunk_start = time.perf_counter()

            chunk = handle.read(chunk_size)
            if not chunk:
                break

            this_size = len(chunk)
            hasher.update(chunk)

            checked_bytes += this_size
            progressbar.step(checked_bytes)

            if bytes_per_second is not None:
                bytes_per_second.limit(this_size)

            if dynamic_chunk_size:
                chunk_time = time.perf_counter() - chunk_start
                chunk_size = dynamic_chunk_sizer(chunk_size, chunk_time, IDEAL_CHUNK_TIME)

    progressbar.done()
    return hasher

def is_xor(*args):
    '''
    Return True if and only if one arg is truthy.
    '''
    return [bool(a) for a in args].count(True) == 1

def limiter_or_none(value):
    '''
    Returns a Ratelimiter object if the argument can be normalized to one,
    or None if the argument is None. Saves the caller from having to if.
    '''
    if value is None:
        return None

    if isinstance(value, ratelimiter.Ratelimiter):
        return value

    if isinstance(value, str):
        value = bytestring.parsebytes(value)

    if not isinstance(value, (int, float)):
        raise TypeError(type(value))

    limiter = ratelimiter.Ratelimiter(allowance=value, period=1)
    return limiter

def new_root(filepath, root):
    '''
    Prepend `root` to `filepath`, drive letter included. For example:
    "C:\\folder\\subfolder\\file.txt" and "D:\\backups" becomes
    "D:\\backups\\C\\folder\\subfolder\\file.txt"

    I use this so that my G: drive can have backups from my C: and D: drives
    while preserving directory structure in G:\\D and G:\\C.
    '''
    filepath = pathclass.Path(filepath).absolute_path.replace(':', os.sep)
    new_path = pathclass.Path(root).join(filepath)
    return new_path

def normalize(text):
    '''
    Apply os.path.normpath and os.path.normcase.
    '''
    return os.path.normpath(os.path.normcase(text))

def verify_hash(
        path,
        hash_class,
        known_hash,
        *,
        known_size=None,
        **hash_kwargs,
    ):
    '''
    Calculate the file's hash and compare it against a previous known hash.
    Raises HashVerificationFailed if they differ, returns None if they match.

    hash_class:
        Should be a hashlib class or a callable that returns an instance of one.

    known_hash:
        Should be the hexdigest string from the previously calculated hash.

    known_size:
        Optional, should be the previously known integer number of bytes.
        This makes failing the file much easier if the sizes differ.

    **hash_kwargs:
        Passed into `hash_file`.
    '''
    path = pathclass.Path(path)
    path.assert_is_file()

    log.debug('Verifying hash for "%s" against %s.', path.absolute_path, known_hash)

    if known_size is not None:
        file_size = path.size
        if file_size != known_size:
            raise HashVerificationFailed(f'File size {file_size} != known size {known_size}.')

    file_hash = hash_file(path, hash_class=hash_class, **hash_kwargs)
    digest = file_hash.hexdigest()
    if digest != known_hash:
        raise HashVerificationFailed(f'File hash "{digest}" != known hash "{known_hash}".')

    log.debug('Hash verification passed.')
    return file_hash

# For the purpose of allowing the copy_file function to have an argument called
# verify_hash, we need to have an alternate name by which to call the function.
_verify_hash = verify_hash

def walk(
        path='.',
        *,
        callback_permission_denied=None,
        exclude_directories=None,
        exclude_filenames=None,
        glob_directories=None,
        glob_filenames=None,
        recurse=True,
        sort=False,
        yield_directories=False,
        yield_files=True,
        yield_style=YIELD_STYLE_FLAT,
    ):
    '''
    Yield pathclass.Path objects for files in the tree, similar to os.walk.

    callback_permission_denied:
        If OSErrors (Permission Denied) occur when trying to list a directory,
        your function will be called with the exception object as the only
        argument.

    exclude_directories:
        A set of directories that will not be yielded. Members can be absolute
        paths, glob patterns, or just plain names.
        For example: {'C:\\folder', '*_small', 'thumbnails'}

    exclude_filenames:
        A set of filenames that will not be yielded. Members can be absolute
        paths, glob patterns, or just plain names.
        For example: {'C:\\folder\\file.txt', '*.temp', 'desktop.ini'}

    glob_directories:
        A set of glob patterns. Directories will only be yielded if they match
        at least one of these patterns. Directories which do not match these
        patterns will still be used for traversal, though.

    glob_filenames:
        A set of glob patterns. Filenames will only be yielded if they match
        at least one of these patterns.

    recurse:
        If False, we will yield only the items from the starting path and then
        stop. This might seem silly for a walk function, but it makes it easier
        on the calling side to have a recurse/no-recurse option without having
        to call a separate function with different arguments for each case,
        while still taking advantage of the other filtering features here.

    sort:
        If True, items are sorted before they are yielded. Otherwise, they
        come in whatever order the filesystem returns them, which may not
        be alphabetical.

    yield_directories:
        Should the generator produce directories? True or False.
        Has no effect in nested yield style.

    yield_files:
        Should the generator produce files? True or False.
        Has no effect in nested yield style.

    yield_style:
        If 'flat', yield individual files and directories one by one.
        If 'nested', yield tuple(root, directories, files) like os.walk does,
        except using pathclass.Path objects for everything.

    raises pathclass.NotDirectory if the starting path is not an existing
    directory.
    '''
    if not yield_directories and not yield_files:
        raise ValueError('yield_directories and yield_files cannot both be False.')

    yield_style = {
        'flat': YIELD_STYLE_FLAT,
        'nested': YIELD_STYLE_NESTED,
    }.get(yield_style, yield_style)

    if yield_style not in [YIELD_STYLE_FLAT, YIELD_STYLE_NESTED]:
        raise ValueError(f'yield_style should be "flat" or "nested", not {yield_style}.')

    callback_permission_denied = callback_permission_denied or None

    if exclude_filenames is not None:
        exclude_filenames = {normalize(f) for f in exclude_filenames}

    if exclude_directories is not None:
        exclude_directories = {normalize(f) for f in exclude_directories}

    if glob_filenames is None:
        pass
    elif isinstance(glob_filenames, str):
        glob_filenames = {glob_filenames}
    else:
        glob_filenames = set(glob_filenames)

    if glob_directories is None:
        pass
    elif isinstance(glob_directories, str):
        glob_directories = {glob_directories}
    else:
        glob_directories = set(glob_directories)

    path = pathclass.Path(path)
    path.assert_is_directory()
    path.correct_case()

    def handle_exclusion(whitelist, blacklist, basename, abspath):
        exclude = False

        if whitelist is not None and not exclude:
            exclude = not any(winglob.fnmatch(basename, whitelisted) for whitelisted in whitelist)

        if blacklist is not None and not exclude:
            n_basename = os.path.normcase(basename)
            n_abspath = os.path.normcase(abspath)

            exclude = any(
                n_basename == blacklisted or
                n_abspath == blacklisted or
                winglob.fnmatch(n_basename, blacklisted)
                for blacklisted in blacklist
            )

        return exclude

    # If for some reason the given starting directory is excluded by the
    # exclude parameters.
    if handle_exclusion(None, exclude_directories, path.basename, path.absolute_path):
        return

    # In the following loop, I found joining the os.sep with fstrings to be
    # 10x faster than `os.path.join`, reducing a 6.75 second walk to 5.7.
    # Because we trust the values of current_location and the child names,
    # we don't run the risk of producing bad values this way.

    queue = collections.deque()
    queue.append(path)
    while queue:
        current = queue.pop()
        log.debug('Scanning %s.', current.absolute_path)
        current_rstrip = current.absolute_path.rstrip(os.sep)

        if yield_style is YIELD_STYLE_NESTED:
            child_dirs = []
            child_files = []

        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError) as exc:
            if callback_permission_denied is not None:
                callback_permission_denied(exc)
                continue
            else:
                raise

        if sort:
            entries = sorted(entries, key=lambda e: os.path.normcase(e.name))

        # The problem with stack-based depth-first search is that the last item
        # from the parent dir becomes the first to be walked, leading to
        # reverse-alphabetical order directory traversal. But we also don't
        # want to reverse the input entries because then the files come out
        # backwards. So instead we keep a more_queue to which we appendleft so
        # that it's backwards, and popping will make it forward again.
        more_queue = collections.deque()
        for entry in entries:
            entry_abspath = f'{current_rstrip}{os.sep}{entry.name}'

            if entry.is_dir():
                if handle_exclusion(
                        whitelist=glob_directories,
                        blacklist=exclude_directories,
                        basename=entry.name,
                        abspath=entry_abspath,
                    ):
                    continue

                child = current.with_child(entry.name, _case_correct=True)
                if yield_directories and yield_style is YIELD_STYLE_FLAT:
                    yield child
                elif yield_style is YIELD_STYLE_NESTED:
                    child_dirs.append(child)

                if recurse:
                    more_queue.appendleft(child)

            elif entry.is_file():
                if handle_exclusion(
                        whitelist=glob_filenames,
                        blacklist=exclude_filenames,
                        basename=entry.name,
                        abspath=entry_abspath,
                    ):
                    continue

                child = current.with_child(entry.name, _case_correct=True)
                if yield_files and yield_style is YIELD_STYLE_FLAT:
                    yield child
                elif yield_style is YIELD_STYLE_NESTED:
                    child_files.append(child)

        queue.extend(more_queue)

        if yield_style is YIELD_STYLE_NESTED:
            yield (current, child_dirs, child_files)

# Backwards compatibility
walk_generator = walk
