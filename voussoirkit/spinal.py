import hashlib
import logging
import os
import shutil
import sys

# pip install voussoirkit
from voussoirkit import bytestring
from voussoirkit import pathclass
from voussoirkit import ratelimiter

logging.basicConfig(level=logging.CRITICAL)
log = logging.getLogger(__name__)

# Number of bytes to read and write at a time
CHUNK_SIZE = 2 * bytestring.MIBIBYTE

HASH_CLASS = hashlib.md5

class DestinationIsDirectory(Exception):
    pass

class DestinationIsFile(Exception):
    pass

class RecursiveDirectory(Exception):
    pass

class SourceNotDirectory(Exception):
    pass

class SourceNotFile(Exception):
    pass

class SpinalError(Exception):
    pass

class ValidationError(Exception):
    pass

def callback_exclusion_v1(name, path_type):
    '''
    Example of an exclusion callback function.
    '''
    print('Excluding', path_type, name)

def callback_v1(fpobj, written_bytes, total_bytes):
    '''
    Example of a copy callback function.

    Prints "filename written/total (percent%)"
    '''
    filename = fpobj.absolute_path.encode('ascii', 'replace').decode()
    if written_bytes >= total_bytes:
        ends = '\r\n'
    else:
        ends = ''
    percent = (100 * written_bytes) / max(total_bytes, 1)
    percent = '%07.3f' % percent
    written = '{:,}'.format(written_bytes)
    total = '{:,}'.format(total_bytes)
    written = written.rjust(len(total), ' ')
    status = '{filename} {written}/{total} ({percent}%)\r'
    status = status.format(filename=filename, written=written, total=total, percent=percent)
    print(status, end=ends)
    sys.stdout.flush()

def copy(source, file_args=None, file_kwargs=None, dir_args=None, dir_kwargs=None):
    '''
    Perform copy_dir or copy_file as appropriate for the source path.
    '''
    source = pathclass.Path(source)
    if source.is_file:
        file_args = file_args or tuple()
        file_kwargs = file_kwargs or dict()
        return copy_file(source, *file_args, **file_kwargs)
    elif source.is_dir:
        dir_args = dir_args or tuple()
        dir_kwargs = dir_kwargs or dict()
        return copy_dir(source, *dir_args, **dir_kwargs)
    raise SpinalError('Neither file nor dir: %s' % source)

def copy_dir(
        source,
        destination=None,
        *,
        bytes_per_second=None,
        callback_directory=None,
        callback_exclusion=None,
        callback_file=None,
        callback_permission_denied=None,
        chunk_size=CHUNK_SIZE,
        destination_new_root=None,
        dry_run=False,
        exclude_directories=None,
        exclude_filenames=None,
        files_per_second=None,
        overwrite_old=True,
        precalcsize=False,
        validate_hash=False,
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
        Restrict file copying to this many bytes per second. Can be an integer
        or an existing Ratelimiter object.
        The BYTE, KIBIBYTE, etc constants from module 'bytestring' may help.

        Default = None

    callback_directory:
        This function will be called after each file copy with three parameters:
        name of file copied, number of bytes written to destination directory
        so far, total bytes needed (based on precalcsize).
        If `precalcsize` is False, this function will receive written bytes
        for both written and total, showing 100% always.

        Default = None

    callback_exclusion:
        Passed directly into `walk_generator`.

        Default = None

    callback_file:
        Will be passed into each individual `copy_file` operation as the
        `callback` for that file.

        Default = None

    callback_permission_denied:
        Will be passed into each individual `copy_file` operation as the
        `callback_permission_denied` for that file.

        Default = None

    destination_new_root:
        Determine the destination path by calling
        `new_root(source, destination_new_root)`.
        Thus, this path acts as a root and the rest of the path is matched.

        `destination` and `destination_new_root` are mutually exclusive.

    dry_run:
        Do everything except the actual file copying.

        Default = False

    exclude_filenames:
        Passed directly into `walk_generator`.

        Default = None

    exclude_directories:
        Passed directly into `walk_generator`.

        Default = None

    files_per_second:
        Maximum number of files to be processed per second. Helps to keep CPU
        usage low.

        Default = None

    overwrite_old:
        If True, overwrite the destination file if the source file
        has a more recent "last modified" timestamp.

        Default = True

    precalcsize:
        If True, calculate the size of source before beginning the
        operation. This number can be used in the callback_directory function.
        Else, callback_directory will receive written bytes as total bytes
        (showing 100% always).
        This can take a long time.

        Default = False

    validate_hash:
        Passed directly into each `copy_file`.

    Returns: [destination path, number of bytes written to destination]
    (Written bytes is 0 if all files already existed.)
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

    callback_directory = callback_directory or do_nothing
    bytes_per_second = limiter_or_none(bytes_per_second)
    files_per_second = limiter_or_none(files_per_second)

    # Copy
    written_bytes = 0
    walker = walk_generator(
        source,
        callback_exclusion=callback_exclusion,
        exclude_directories=exclude_directories,
        exclude_filenames=exclude_filenames,
    )
    for source_file in walker:
        if source_file.is_link:
            continue

        destination_abspath = source_file.absolute_path.replace(
            source.absolute_path,
            destination.absolute_path
        )
        destination_file = pathclass.Path(destination_abspath)

        if destination_file.is_dir:
            raise DestinationIsDirectory(destination_file)

        if not dry_run:
            os.makedirs(destination_file.parent.absolute_path, exist_ok=True)

        copied = copy_file(
            source_file,
            destination_file,
            bytes_per_second=bytes_per_second,
            callback_progress=callback_file,
            callback_permission_denied=callback_permission_denied,
            chunk_size=chunk_size,
            dry_run=dry_run,
            overwrite_old=overwrite_old,
            validate_hash=validate_hash,
        )

        copiedname = copied[0]
        written_bytes += copied[1]

        if precalcsize is False:
            callback_directory(copiedname, written_bytes, written_bytes)
        else:
            callback_directory(copiedname, written_bytes, total_bytes)

        if files_per_second is not None:
            files_per_second.limit(1)

    return [destination, written_bytes]

def copy_file(
        source,
        destination=None,
        *,
        destination_new_root=None,
        bytes_per_second=None,
        callback_progress=None,
        callback_permission_denied=None,
        callback_validate_hash=None,
        chunk_size=CHUNK_SIZE,
        dry_run=False,
        overwrite_old=True,
        validate_hash=False,
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
        Restrict file copying to this many bytes per second. Can be an integer
        or an existing Ratelimiter object.
        The provided BYTE, KIBIBYTE, etc constants may help.

        Default = None

    callback_permission_denied:
        If provided, this function will be called when a source file denies
        read access, with the file path and the exception object as parameters.
        THE OPERATION WILL RETURN NORMALLY.

        If not provided, the PermissionError is raised.

        Default = None

    callback_progress:
        If provided, this function will be called after writing
        each chunk_size bytes to destination with three parameters:
        the Path object being copied, number of bytes written so far,
        total number of bytes needed.

        Default = None

    callback_validate_hash:
        Passed directly into `verify_hash`

        Default = None

    dry_run:
        Do everything except the actual file copying.

        Default = False

    overwrite_old:
        If True, overwrite the destination file if the source file
        has a more recent "last modified" timestamp.

        Default = True

    validate_hash:
        If True, verify the file hash of the resulting file, using the
        `HASH_CLASS` global.

        Default = False

    Returns: [destination filename, number of bytes written to destination]
    (Written bytes is 0 if the file already existed.)
    '''
    # Prepare parameters
    if not is_xor(destination, destination_new_root):
        message = 'One and only one of `destination` and '
        message += '`destination_new_root` can be passed'
        raise ValueError(message)

    source = pathclass.Path(source)

    if not source.is_file:
        raise SourceNotFile(source)

    if destination_new_root is not None:
        source.correct_case()
        destination = new_root(source, destination_new_root)
    destination = pathclass.Path(destination)

    callback_progress = callback_progress or do_nothing

    if destination.is_dir:
        destination = destination.with_child(source.basename)

    bytes_per_second = limiter_or_none(bytes_per_second)

    # Determine overwrite
    if destination.exists:
        if overwrite_old is False:
            return [destination, 0]

        source_modtime = source.stat.st_mtime
        destination_modtime = destination.stat.st_mtime
        if source_modtime == destination_modtime:
            return [destination, 0]

    # Copy
    if dry_run:
        if callback_progress is not None:
            callback_progress(destination, 0, 0)
        return [destination, 0]

    source_bytes = source.size
    destination_location = os.path.split(destination.absolute_path)[0]
    os.makedirs(destination_location, exist_ok=True)

    def handlehelper(path, mode):
        try:
            handle = open(path.absolute_path, mode)
            return handle
        except PermissionError as exception:
            if callback_permission_denied is not None:
                callback_permission_denied(path, exception)
                return None
            else:
                raise

    log.debug('Opening handles.')
    source_handle = handlehelper(source, 'rb')
    destination_handle = handlehelper(destination, 'wb')
    if None in (source_handle, destination_handle):
        return [destination, 0]

    if validate_hash:
        hasher = HASH_CLASS()

    written_bytes = 0
    while True:
        try:
            data_chunk = source_handle.read(chunk_size)
        except PermissionError as exception:
            if callback_permission_denied is not None:
                callback_permission_denied(source, exception)
                return [destination, 0]
            else:
                raise
        data_bytes = len(data_chunk)
        if data_bytes == 0:
            break

        if validate_hash:
            hasher.update(data_chunk)

        destination_handle.write(data_chunk)
        written_bytes += data_bytes

        if bytes_per_second is not None:
            bytes_per_second.limit(data_bytes)

        callback_progress(destination, written_bytes, source_bytes)

    if written_bytes == 0:
        # For zero-length files, we want to get at least one call in there.
        callback_progress(destination, written_bytes, source_bytes)

    # Fin
    log.debug('Closing source handle.')
    source_handle.close()
    log.debug('Closing dest handle.')
    destination_handle.close()
    log.debug('Copying metadata')
    shutil.copystat(source.absolute_path, destination.absolute_path)

    if validate_hash:
        verify_hash(
            destination,
            callback=callback_validate_hash,
            known_size=source_bytes,
            known_hash=hasher.hexdigest(),
        )

    return [destination, written_bytes]

def do_nothing(*args):
    '''
    Used by other functions as the default callback.
    '''
    return

def get_dir_size(path):
    '''
    Calculate the total number of bytes across all files in this directory
    and its subdirectories.
    '''
    path = pathclass.Path(path)

    if not path.is_dir:
        raise SourceNotDirectory(path)

    total_bytes = 0
    for filepath in walk_generator(path):
        total_bytes += filepath.size

    return total_bytes

def is_subfolder(parent, child):
    '''
    Determine whether parent contains child.
    '''
    parent = normalize(pathclass.Path(parent).absolute_path) + os.sep
    child = normalize(pathclass.Path(child).absolute_path) + os.sep
    return child.startswith(parent)

def is_xor(*args):
    '''
    Return True if and only if one arg is truthy.
    '''
    return [bool(a) for a in args].count(True) == 1

def limiter_or_none(value):
    if isinstance(value, str):
        value = bytestring.parsebytes(value)
    if isinstance(value, ratelimiter.Ratelimiter):
        limiter = value
    elif value is not None:
        limiter = ratelimiter.Ratelimiter(allowance=value, period=1)
    else:
        limiter = None
    return limiter

def new_root(filepath, root):
    '''
    Prepend `root` to `filepath`, drive letter included. For example:
    "C:\\folder\\subfolder\\file.txt" and "C:\\backups" becomes
    "C:\\backups\\C\\folder\\subfolder\\file.txt"

    I use this so that my G: drive can have backups from my C: and D: drives
    while preserving directory structure in G:\\D and G:\\C.
    '''
    filepath = pathclass.Path(filepath).absolute_path
    root = pathclass.Path(root).absolute_path
    filepath = filepath.replace(':', os.sep)
    filepath = os.path.normpath(filepath)
    filepath = os.path.join(root, filepath)
    return pathclass.Path(filepath)

def normalize(text):
    '''
    Apply os.path.normpath and os.path.normcase.
    '''
    return os.path.normpath(os.path.normcase(text))

def verify_hash(path, known_size, known_hash, callback=None):
    '''
    callback:
        A function that takes three parameters:
        path object, bytes ingested so far, bytes total
    '''
    path = pathclass.Path(path)
    log.debug('Validating hash for "%s" against %s', path.absolute_path, known_hash)
    file_size = os.path.getsize(path.absolute_path)
    if file_size != known_size:
        raise ValidationError('File size %d != known size %d' % (file_size, known_size))
    handle = open(path.absolute_path, 'rb')
    hasher = HASH_CLASS()
    checked_bytes = 0
    with handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            checked_bytes += len(chunk)
            if callback is not None:
                callback(path, checked_bytes, file_size)

    file_hash = hasher.hexdigest()
    if file_hash != known_hash:
        raise ValidationError('File hash "%s" != known hash "%s"' % (file_hash, known_hash))
    log.debug('Hash validation passed.')


def walk_generator(
        path='.',
        *,
        callback_exclusion=None,
        callback_permission_denied=None,
        exclude_directories=None,
        exclude_filenames=None,
        recurse=True,
        yield_directories=False,
        yield_files=True,
        yield_style='flat',
    ):
    '''
    Yield Path objects for files in the file tree, similar to os.walk.

    callback_exclusion:
        This function will be called when a file or directory is excluded with
        two parameters: the path, and 'file' or 'directory'.

        Default = None

    exclude_filenames:
        A set of filenames that will not be copied. Entries can be absolute
        paths to exclude that particular file, or plain names to exclude
        all matches. For example:
        {'C:\\folder\\file.txt', 'desktop.ini'}

        Default = None

    exclude_directories:
        A set of directories that will not be copied. Entries can be
        absolute paths to exclude that particular directory, or plain names
        to exclude all matches. For example:
        {'C:\\folder', 'thumbnails'}

        Default = None

    recurse:
        Yield from subdirectories. If False, only immediate files are returned.

    yield_directories:
        Should the generator produce directories? Has no effect in nested yield style.

    yield_files:
        Should the generator produce files? Has no effect in nested yield style.

    yield_style:
        If 'flat', yield individual files one by one in a constant stream.
        If 'nested', yield tuple(root, directories, files) like os.walk does,
            except I use Path objects with absolute paths for everything.
    '''
    if not yield_directories and not yield_files:
        raise ValueError('yield_directories and yield_files cannot both be False.')

    if yield_style not in ['flat', 'nested']:
        raise ValueError(f'yield_style should be "flat" or "nested", not {yield_style}.')

    if exclude_directories is None:
        exclude_directories = set()

    if exclude_filenames is None:
        exclude_filenames = set()

    callback_exclusion = callback_exclusion or do_nothing
    callback_permission_denied = callback_permission_denied or do_nothing
    _callback_permission_denied = callback_permission_denied
    def callback_permission_denied(error):
        return _callback_permission_denied(error.filename, error)

    exclude_filenames = {normalize(f) for f in exclude_filenames}
    exclude_directories = {normalize(f) for f in exclude_directories}

    path = pathclass.Path(path)
    path.correct_case()

    exclude = (
        path.basename in exclude_directories or
        path.absolute_path in exclude_directories
    )
    if exclude:
        callback_exclusion(path, 'directory')
        return

    def handle_exclusion(blacklist, basename, abspath, kind):
        exclude = (
            os.path.normcase(basename) in blacklist or
            os.path.normcase(abspath) in blacklist
        )
        if exclude:
            callback_exclusion(abspath, kind)
            return 1

    # In the following loops, I found joining the os.sep with fstrings to be
    # 10x faster than `os.path.join`, reducing a 6.75 second walk to 5.7.
    # Because we trust the values of current_location and the child names,
    # we don't run the risk of producing bad values this way.

    def walkstep_nested(current_location, child_dirs, child_files):
        directories = []
        new_child_dirs = []
        for child_dir in child_dirs:
            child_dir_abspath = f'{current_location}{os.sep}{child_dir}'
            if handle_exclusion(exclude_directories, child_dir, child_dir_abspath, 'directory'):
                continue

            new_child_dirs.append(child_dir)
            directories.append(pathclass.Path(child_dir_abspath))

        # This will actually affect the results of the os.walk going forward!
        child_dirs[:] = new_child_dirs

        files = []
        for child_file in child_files:
            child_file_abspath = f'{current_location}{os.sep}{child_file}'
            if handle_exclusion(exclude_filenames, child_file, child_file_abspath, 'file'):
                continue

            files.append(pathclass.Path(child_file_abspath))

        current_location = pathclass.Path(current_location)
        yield (current_location, directories, files)

    def walkstep_flat(current_location, child_dirs, child_files):
        new_child_dirs = []
        for child_dir in child_dirs:
            child_dir_abspath = f'{current_location}{os.sep}{child_dir}'
            if handle_exclusion(exclude_directories, child_dir, child_dir_abspath, 'directory'):
                continue

            new_child_dirs.append(child_dir)
            if yield_directories:
                yield pathclass.Path(child_dir_abspath)

        # This will actually affect the results of the os.walk going forward!
        child_dirs[:] = new_child_dirs

        if yield_files:
            for child_file in child_files:
                child_file_abspath = f'{current_location}{os.sep}{child_file}'
                if handle_exclusion(exclude_filenames, child_file, child_file_abspath, 'file'):
                    continue

                yield pathclass.Path(child_file_abspath)

    walker = os.walk(path.absolute_path, onerror=callback_permission_denied)
    if yield_style == 'flat':
        for step in walker:
            yield from walkstep_flat(*step)
            if not recurse:
                break

    if yield_style == 'nested':
        for step in walker:
            yield from walkstep_nested(*step)
            if not recurse:
                break
