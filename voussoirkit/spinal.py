import hashlib
import logging
import os
import shutil
import sys

from voussoirkit import bytestring
from voussoirkit import dotdict
from voussoirkit import pathclass
from voussoirkit import ratelimiter
from voussoirkit import safeprint
from voussoirkit import sentinel
from voussoirkit import vlogging
from voussoirkit import winglob

log = vlogging.getLogger(__name__)

BAIL = sentinel.Sentinel('BAIL')

# Number of bytes to read and write at a time
CHUNK_SIZE = 2 * bytestring.MIBIBYTE

HASH_CLASS = hashlib.md5

class SpinalException(Exception):
    pass

class DestinationIsDirectory(SpinalException):
    pass

class DestinationIsFile(SpinalException):
    pass

class RecursiveDirectory(SpinalException):
    pass

class SourceNotDirectory(SpinalException):
    pass

class SourceNotFile(SpinalException):
    pass

class SpinalError(SpinalException):
    pass

class ValidationError(SpinalException):
    pass

def callback_progress_v1(fpobj, written_bytes, total_bytes):
    '''
    Example of a copy callback function.

    Prints "filename written/total (percent%)"
    '''
    if written_bytes >= total_bytes:
        ends = '\r\n'
    else:
        ends = ''
    percent = (100 * written_bytes) / max(total_bytes, 1)
    percent = f'{percent:07.3f}'
    written = '{:,}'.format(written_bytes)
    total = '{:,}'.format(total_bytes)
    written = written.rjust(len(total), ' ')
    status = f'{fpobj.absolute_path} {written}/{total} ({percent}%)\r'
    safeprint.safeprint(status, end=ends)
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
    raise SpinalError(f'Neither file nor dir: {source}')

def copy_dir(
        source,
        destination=None,
        *,
        bytes_per_second=None,
        callback_directory_progress=None,
        callback_file_progress=None,
        callback_permission_denied=None,
        callback_pre_directory=None,
        callback_pre_file=None,
        chunk_size=CHUNK_SIZE,
        destination_new_root=None,
        dry_run=False,
        exclude_directories=None,
        exclude_filenames=None,
        files_per_second=None,
        overwrite_old=True,
        precalcsize=False,
        skip_symlinks=True,
        stop_event=None,
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
        Passed into each `copy_file` as `bytes_per_second`.

    callback_directory_progress:
        This function will be called after each file copy with three arguments:
        name of file copied, number of bytes written to destination directory
        so far, total bytes needed (based on precalcsize).
        If `precalcsize` is False, this function will receive written bytes
        for both written and total, showing 100% always.

    callback_file_progress:
        Passed into each `copy_file` as `callback_progress`.

    callback_permission_denied:
        Passed into each `copy_file` as `callback_permission_denied`.

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

    destination_new_root:
        Determine the destination path by calling
        `new_root(source, destination_new_root)`.
        Thus, this path acts as a root and the rest of the path is matched.

        `destination` and `destination_new_root` are mutually exclusive.

    dry_run:
        Do everything except the actual file copying.

    exclude_filenames:
        Passed directly into `walk`.

    exclude_directories:
        Passed directly into `walk`.

    files_per_second:
        Maximum number of files to be processed per second. Helps to keep CPU
        usage low.

    overwrite_old:
        Passed into each `copy_file` as `overwrite_old`.

    precalcsize:
        If True, calculate the size of source before beginning the copy.
        This number can be used in the callback_directory_progress function.
        Else, callback_directory_progress will receive written bytes as total
        bytes (showing 100% always).
        This may take a while if the source directory is large.

    skip_symlinks:
        If True, symlink dirs are skipped and symlink files are not copied.

    stop_event:
        If provided, a threading.Event object which when set indicates that we
        should finish the current file and then stop the remainder of the copy.
        For example, you can run this function in a thread and let the main
        thread catch ctrl+c to set the stop_event, so the copy can stop cleanly.

    validate_hash:
        Passed directly into each `copy_file`.

    Returns a dotdict containing at least `destination` and `written_bytes`.
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

    callback_directory_progress = callback_directory_progress or do_nothing
    callback_pre_directory = callback_pre_directory or do_nothing
    callback_pre_file = callback_pre_file or do_nothing
    bytes_per_second = limiter_or_none(bytes_per_second)
    files_per_second = limiter_or_none(files_per_second)

    # Copy
    walker = walk(
        source,
        exclude_directories=exclude_directories,
        exclude_filenames=exclude_filenames,
        yield_style='nested',
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

            for source_file in files:
                destination_file = destination_dir.with_child(source_file.basename)
                yield (source_file, destination_file)

    walker = denester(walker)
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
            callback_progress=callback_file_progress,
            callback_permission_denied=callback_permission_denied,
            callback_pre_copy=callback_pre_file,
            chunk_size=chunk_size,
            dry_run=dry_run,
            overwrite_old=overwrite_old,
            validate_hash=validate_hash,
        )

        written_bytes += copied.written_bytes

        if precalcsize is False:
            callback_directory_progress(copied.destination, written_bytes, written_bytes)
        else:
            callback_directory_progress(copied.destination, written_bytes, total_bytes)

        if files_per_second is not None:
            files_per_second.limit(1)

    results = dotdict.DotDict({
        'destination': destination,
        'written_bytes': written_bytes,
    })
    return results

def copy_file(
        source,
        destination=None,
        *,
        destination_new_root=None,
        bytes_per_second=None,
        callback_progress=None,
        callback_permission_denied=None,
        callback_pre_copy=None,
        callback_validate_hash=None,
        chunk_size=CHUNK_SIZE,
        dry_run=False,
        hash_class=None,
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

    callback_progress:
        If provided, this function will be called after writing
        each chunk_size bytes to destination with three parameters:
        the Path object being copied, number of bytes written so far,
        total number of bytes needed.

    callback_hash_progress:
        Passed into `hash_file` as callback_progress when validating the hash.

    dry_run:
        Do everything except the actual file copying.

    hash_class:
        If provided, should be a hashlib class or a callable that returns an
        instance of one. The hash will be computed while the file is being
        copied, and returned in the dotdict as `hash`.
        Note that if the function returns early due to dry_run or file not
        needing overwrite, this won't be set, so be prepared to handle None.
        If None, the hash will not be calculated.

    overwrite_old:
        If True, overwrite the destination file if the source file
        has a more recent "last modified" timestamp.
        If False, existing files will be skipped no matter what.

    validate_hash:
        If True, the copied file will be read back after the copy is complete,
        and its hash will be compared against the hash of the source file.
        If hash_class is None, then the global HASH_CLASS is used.

    Returns a dotdict containing at least `destination` and `written_bytes`.
    (Written bytes is 0 if the file already existed.)
    '''
    # Prepare parameters
    if not is_xor(destination, destination_new_root):
        message = 'One and only one of `destination` and '
        message += '`destination_new_root` can be passed'
        raise ValueError(message)

    source = pathclass.Path(source)
    source.correct_case()

    if not source.is_file:
        raise SourceNotFile(source)

    if destination_new_root is not None:
        destination = new_root(source, destination_new_root)
    destination = pathclass.Path(destination)

    callback_progress = callback_progress or do_nothing
    callback_pre_copy = callback_pre_copy or do_nothing

    if destination.is_dir:
        destination = destination.with_child(source.basename)

    bytes_per_second = limiter_or_none(bytes_per_second)

    results = dotdict.DotDict({
        'destination': destination,
        'written_bytes': 0,
    }, default=None)

    # Determine overwrite
    if destination.exists:
        if not overwrite_old:
            return results

        source_modtime = source.stat.st_mtime
        destination_modtime = destination.stat.st_mtime
        if source_modtime == destination_modtime:
            return results

    # Copy
    if dry_run:
        if callback_progress is not None:
            callback_progress(destination, 0, 0)
        return results

    source_bytes = source.size

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

    log.debug('Opening handles.')
    source_handle = handlehelper(source, 'rb')
    destination_handle = handlehelper(destination, 'wb')

    if source_handle is None and destination_handle:
        destination_handle.close()
        return results

    if destination_handle is None:
        source_handle.close()
        return results

    if hash_class is not None:
        results.hash = hash_class()
    elif validate_hash:
        hash_class = HASH_CLASS
        results.hash = HASH_CLASS()

    while True:
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

        callback_progress(destination, results.written_bytes, source_bytes)

        if bytes_per_second is not None:
            bytes_per_second.limit(data_bytes)

    if results.written_bytes == 0:
        # For zero-length files, we want to get at least one call in there.
        callback_progress(destination, results.written_bytes, source_bytes)

    # Fin
    log.debug('Closing source handle.')
    source_handle.close()
    log.debug('Closing dest handle.')
    destination_handle.close()
    log.debug('Copying metadata.')
    shutil.copystat(source.absolute_path, destination.absolute_path)

    if validate_hash:
        verify_hash(
            destination,
            callback_progress=callback_hash_progress,
            hash_class=hash_class,
            known_hash=results.hash.hexdigest(),
            known_size=source_bytes,
        )

    return results

def do_nothing(*args, **kwargs):
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
    for filepath in walk(path):
        total_bytes += filepath.size

    return total_bytes

def hash_file(
        path,
        hash_class,
        *,
        bytes_per_second=None,
        callback_progress=None,
        chunk_size=CHUNK_SIZE,
    ):
    '''
    hash_class:
        Should be a hashlib class or a callable that returns an instance of one.

    callback_progress:
        A function that takes three parameters:
        path object, bytes ingested so far, bytes total
    '''
    path = pathclass.Path(path)
    path.assert_is_file()
    hasher = hash_class()

    bytes_per_second = limiter_or_none(bytes_per_second)
    callback_progress = callback_progress or do_nothing

    checked_bytes = 0
    file_size = path.size

    handle = path.open('rb')
    with handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break

            this_size = len(chunk)
            hasher.update(chunk)

            checked_bytes += this_size
            callback_progress(path, checked_bytes, file_size)

            if bytes_per_second is not None:
                bytes_per_second.limit(this_size)

    return hasher

def is_xor(*args):
    '''
    Return True if and only if one arg is truthy.
    '''
    return [bool(a) for a in args].count(True) == 1

def limiter_or_none(value):
    if isinstance(value, ratelimiter.Ratelimiter):
        return value

    if value is None:
        return None

    if isinstance(value, str):
        value = bytestring.parsebytes(value)

    if not isinstance(value, (int, float)):
        raise TypeError(type(value))

    limiter = ratelimiter.Ratelimiter(allowance=value, period=1)
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

def verify_hash(
        path,
        hash_class,
        known_hash,
        *,
        known_size=None,
        **hash_kwargs,
    ):
    path = pathclass.Path(path)
    path.assert_is_file()

    log.debug('Validating hash for "%s" against %s.', path.absolute_path, known_hash)

    if known_size is not None:
        file_size = path.size
        if file_size != known_size:
            raise ValidationError(f'File size {file_size} != known size {known_size}.')

    file_hash = hash_file(path, hash_class=hash_class, **hash_kwargs).hexdigest()
    if file_hash != known_hash:
        raise ValidationError(f'File hash "{file_hash}" != known hash "{known_hash}".')

    log.debug('Hash validation passed.')

def walk(
        path='.',
        *,
        callback_permission_denied=None,
        exclude_directories=None,
        exclude_filenames=None,
        glob_directories=None,
        glob_filenames=None,
        recurse=True,
        yield_directories=False,
        yield_files=True,
        yield_style='flat',
    ):
    '''
    Yield pathclass.Path objects for files in the tree, similar to os.walk.

    callback_permission_denied:
        Passed directly into os.walk as onerror. If OSErrors (Permission Denied)
        occur when trying to list a directory, your function will be called with
        the exception object as the only argument.

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
        at least one of these patterns.

    glob_filenames:
        A set of glob patterns. Filenames will only be yielded if they match
        at least one of these patterns.

    recurse:
        Yield from subdirectories. If False, only immediate files are returned.

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
    '''
    if not yield_directories and not yield_files:
        raise ValueError('yield_directories and yield_files cannot both be False.')

    if yield_style not in ['flat', 'nested']:
        raise ValueError(f'yield_style should be "flat" or "nested", not {yield_style}.')

    callback_permission_denied = callback_permission_denied or do_nothing

    if exclude_filenames is not None:
        exclude_filenames = {normalize(f) for f in exclude_filenames}

    if exclude_directories is not None:
        exclude_directories = {normalize(f) for f in exclude_directories}

    if glob_filenames is not None:
        glob_filenames = set(glob_filenames)

    if glob_directories is not None:
        glob_directories = set(glob_directories)

    path = pathclass.Path(path)
    path.correct_case()

    def handle_exclusion(whitelist, blacklist, basename, abspath):
        exclude = False

        if whitelist is not None and not exclude:
            exclude = not any(winglob.fnmatch(basename, whitelisted) for whitelisted in whitelist)

        if blacklist is not None and not exclude:
            n_basename = normalize(basename)
            n_abspath = normalize(abspath)

            exclude = any(
                n_basename == blacklisted or
                n_abspath == blacklisted or
                winglob.fnmatch(n_basename, blacklisted)
                for blacklisted in blacklist
            )

        return exclude

    # If for some reason the given starting directory is excluded by the
    # exclude parameters.
    if handle_exclusion(glob_directories, exclude_directories, path.basename, path.absolute_path):
        return

    # In the following loops, I found joining the os.sep with fstrings to be
    # 10x faster than `os.path.join`, reducing a 6.75 second walk to 5.7.
    # Because we trust the values of current_location and the child names,
    # we don't run the risk of producing bad values this way.

    def walkstep_nested(current_location, child_dirs, child_files):
        directories = []
        new_child_dirs = []
        for child_dir in child_dirs:
            child_dir_abspath = f'{current_location}{os.sep}{child_dir}'
            if handle_exclusion(glob_directories, exclude_directories, child_dir, child_dir_abspath):
                continue

            new_child_dirs.append(child_dir)
            directories.append(pathclass.Path(child_dir_abspath))

        # This will actually affect the results of the os.walk going forward!
        child_dirs[:] = new_child_dirs

        files = []
        for child_file in child_files:
            child_file_abspath = f'{current_location}{os.sep}{child_file}'
            if handle_exclusion(glob_filenames, exclude_filenames, child_file, child_file_abspath):
                continue

            files.append(pathclass.Path(child_file_abspath))

        current_location = pathclass.Path(current_location)
        yield (current_location, directories, files)

    def walkstep_flat(current_location, child_dirs, child_files):
        new_child_dirs = []
        for child_dir in child_dirs:
            child_dir_abspath = f'{current_location}{os.sep}{child_dir}'
            if handle_exclusion(glob_directories, exclude_directories, child_dir, child_dir_abspath):
                continue

            new_child_dirs.append(child_dir)
            if yield_directories:
                yield pathclass.Path(child_dir_abspath)

        # This will actually affect the results of the os.walk going forward!
        child_dirs[:] = new_child_dirs

        if yield_files:
            for child_file in child_files:
                child_file_abspath = f'{current_location}{os.sep}{child_file}'
                if handle_exclusion(glob_filenames, exclude_filenames, child_file, child_file_abspath):
                    continue

                yield pathclass.Path(child_file_abspath)

    walker = os.walk(path.absolute_path, onerror=callback_permission_denied, followlinks=True)
    if yield_style == 'flat':
        my_stepper = walkstep_flat
    if yield_style == 'nested':
        my_stepper = walkstep_nested

    for step in walker:
        yield from my_stepper(*step)
        if not recurse:
            break

# Backwards compatibility
walk_generator = walk
