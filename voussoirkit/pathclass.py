import glob
import os
import shutil

_glob = glob

from voussoirkit import winglob

if os.name == 'nt':
    SEPS = {'\\', '/'}
else:
    SEPS = {'/'}

WINDOWS_GLOBAL_BADCHARS = {'*', '?', '<', '>', '|', '"'}
WINDOWS_BASENAME_BADCHARS = {'\\', '/', ':', '*', '?', '<', '>', '|', '"'}
WINDOWS_RESERVED_NAMES = {
    'AUX',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'CON',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
    'NUL',
    'PRN',
}

class PathclassException(Exception):
    pass

class Exists(PathclassException):
    pass

class IsFile(PathclassException):
    pass

class IsDirectory(PathclassException):
    pass

class IsLink(PathclassException):
    pass

class NotDirectory(PathclassException):
    pass

class NotExists(PathclassException):
    pass

class NotEnoughSpace(PathclassException):
    def __init__(self, free, reserve, path):
        self.free = free
        self.reserve = reserve
        self.path = path
        self.args = (f'Only {free} available of requested {reserve}.',)

class NotFile(PathclassException):
    pass

class NotLink(PathclassException):
    pass

class Drive:
    '''
    The Drive part will contain everything up to but not including the final
    slash. On Unix this will usually just be '', on Windows it will be the
    drive letter 'C:' or the UNC path '\\\\?\\host'
    '''
    def __init__(self, name):
        name = name.rstrip(os.sep)
        self._name = name

    def __eq__(self, other):
        return self._name == other._name

class Extension:
    def __init__(self, ext):
        if isinstance(ext, Extension):
            ext = ext.ext
        ext = self.prep(ext)
        self.ext = ext

    @staticmethod
    def prep(ext):
        return os.path.normcase(ext).lstrip('.')

    def __bool__(self):
        return bool(self.ext)

    def __eq__(self, other):
        if isinstance(other, Extension):
            return self.ext == other.ext
        other = self.prep(other)
        return self.ext == other

    def __hash__(self):
        return hash(self.ext)

    def __repr__(self):
        return f'Extension({repr(self.ext)})'

    def __str__(self):
        return self.ext

    @property
    def no_dot(self):
        return self.ext

    @property
    def with_dot(self):
        if self.ext == '':
            return ''
        return '.' + self.ext

class Path:
    def __init__(
            self,
            path,
            *,
            _case_correct=False,
        ):
        '''
        _case_correct:
            True or False. If True, this indicates that the path casing is
            known in advance to be correct, which means calls to correct_case
            can be skipped. This is helpful because correct_case can be a
            source of slowdown.
        '''
        self._case_correct = _case_correct
        self._absolute_path = None
        self._extension = None

        if isinstance(path, Path):
            self._parts = path._parts
            self._absolute_path = path._absolute_path
            self._extension = path._extension
            return

        if isinstance(path, (tuple, list)):
            if len(path) == 0:
                raise ValueError('Empty tuple')
            drive = normalize_drive(path[0])
            parts = tuple(normalize_pathpart(part) for part in path[1:])
            self._parts = (drive, *parts)
            return

        path = os.fspath(path)

        if isinstance(path, str):
            path = os.path.expanduser(path)
            path = os.path.abspath(path)
            self._absolute_path = path
            (drive, remainder) = os.path.splitdrive(path)
            drive = normalize_drive(drive)
            remainder = remainder.lstrip(os.sep)
            # If remainder == '' then splitting it will yield [''] which we
            # don't want in our parts.
            if remainder:
                parts = (normalize_pathpart(part) for part in remainder.split(os.sep))
                self._parts = (drive, *parts)
            else:
                self._parts = (drive,)
            return

        raise TypeError(f'path must be {Path}, {tuple} or {str}, not {type(path)}.')

    def __contains__(self, other):
        if not isinstance(other, Path):
            other = Path(other)

        # If other is a child of self, then other._parts must be at least as
        # long as self._parts plus one.
        if len(self._parts) >= len(other._parts):
            return False

        # Compare by normcase so that Windows's case-insensitive filenames
        # behave correctly.
        # It would be fitting to do this check using ._parts, but we would
        # have to normcase each part anyway so let's just do the whole string
        # at once.
        return other.normcase.startswith(self.normcase)

    def __eq__(self, other):
        if not isinstance(other, (Path, str, tuple, list)):
            try:
                other = os.fspath(other)
            except TypeError:
                return False

        if not isinstance(other, Path):
            other = Path(other)

        # Compare by normcase so that Windows's case-insensitive filenames
        # behave correctly.
        return self.normcase == other.normcase

    def __fspath__(self):
        return self.absolute_path

    def __hash__(self):
        return hash(self.normcase)

    def __lt__(self, other):
        # Sort by normcase so that Windows's case-insensitive filenames sort
        # alphabetically regardless of case.
        return self.normcase < other.normcase

    def __repr__(self):
        return f'{self.__class__.__name__}({repr(self.absolute_path)})'

    @property
    def absolute_path(self):
        if self._absolute_path is not None:
            return self._absolute_path

        # This ensures that if this Path is just the drive, it will end with
        # the sep, and all other paths do not end with the sep.
        drive = self._parts[0]
        parts = self._parts[1:]
        absolute = drive._name + os.sep + os.sep.join(part._name for part in parts)
        self._absolute_path = absolute
        return self._absolute_path

    def assert_disk_space(self, reserve):
        free = shutil.disk_usage(self).free
        if free < reserve:
            raise NotEnoughSpace(path=self, reserve=reserve, free=free)
        return free

    def assert_exists(self):
        if not self.exists:
            raise NotExists(self)

    def assert_not_exists(self):
        if self.exists:
            raise Exists(self)

    def assert_not_file(self):
        if self.is_file:
            raise IsFile(self)

    def assert_not_directory(self):
        if self.is_dir:
            raise IsDirectory(self)

    assert_not_dir = assert_not_directory

    def assert_not_link(self):
        if self.is_link:
            raise IsLink(self)

    def assert_is_file(self):
        if not self.is_file:
            raise NotFile(self)

    def assert_is_directory(self):
        if not self.is_dir:
            raise NotDirectory(self)

    assert_is_dir = assert_is_directory

    def assert_is_link(self):
        if not self.is_link:
            raise NotLink(self)

    def add_extension(self, extension):
        extension = Extension(extension)
        if extension == '':
            return self
        return self.parent.with_child(self.basename + extension.with_dot)

    @property
    def basename(self):
        return self._parts[-1]._name

    def correct_case(self):
        if self._case_correct:
            return self
        absolute_path = get_path_casing(self.absolute_path)
        self.__init__(absolute_path, _case_correct=True)
        return self

    @property
    def depth(self):
        return len(self._parts)

    @property
    def dot_extension(self):
        return self.extension.with_dot

    @property
    def drive(self):
        return Path([self._parts[0]])

    @property
    def exists(self):
        return os.path.exists(self)

    @property
    def extension(self):
        if self._extension is not None:
            return self._extension

        # Let's consider bare drives to not have an extension.
        if len(self._parts) == 1:
            self._extension = ''
            return self._extension

        self._extension = Extension(os.path.splitext(self.basename)[1])
        return self._extension

    def glob(self, pattern):
        '''
        Return Paths that match a glob pattern within this directory.
        '''
        pattern = normalize_basename_glob(pattern)
        # By sidestepping the glob function and going straight for fnmatch
        # filter, we have slightly different behavior than normal, which is
        # that glob.glob treats .* as hidden files and won't match them with
        # patterns that don't also start with .*.
        children = os.listdir(self)
        children = winglob.fnmatch_filter(children, pattern)
        items = [self.with_child(c, _case_correct=self._case_correct) for c in children]
        return items

    def glob_directories(self, pattern):
        pattern = normalize_basename_glob(pattern)
        # Instead of turning all children into Path objects and filtering by
        # the stat, let's filter by the stat from scandir first.
        children = (e.name for e in os.scandir(self) if e.is_dir())
        children = winglob.fnmatch_filter(children, pattern)
        items = [self.with_child(c, _case_correct=self._case_correct) for c in children]
        return items

    def glob_files(self, pattern):
        pattern = normalize_basename_glob(pattern)
        children = (e.name for e in os.scandir(self) if e.is_file())
        children = winglob.fnmatch_filter(children, pattern)
        items = [self.with_child(c, _case_correct=self._case_correct) for c in children]
        return items

    @property
    def is_directory(self):
        return os.path.isdir(self)

    # Aliases for your convenience.
    is_dir = is_directory
    is_folder = is_directory

    @property
    def is_file(self):
        return os.path.isfile(self)

    @property
    def is_link(self):
        return os.path.islink(self)

    def join(self, subpath, **spawn_kwargs):
        '''
        Use os.path.join to join this path with any other path string.
        '''
        if not isinstance(subpath, str):
            raise TypeError(f'subpath must be a {str}, not {type(subpath)}.')
        path = os.path.join(self.absolute_path, subpath)
        return Path(path, **spawn_kwargs)

    def listdir(self):
        children = os.listdir(self)
        children = [self.with_child(child, _case_correct=self._case_correct) for child in children]
        return children

    def listdir_directories(self):
        children = (e.name for e in os.scandir(self) if e.is_dir())
        items = [self.with_child(c, _case_correct=self._case_correct) for c in children]
        return items

    def listdir_files(self):
        children = (e.name for e in os.scandir(self) if e.is_file())
        items = [self.with_child(c, _case_correct=self._case_correct) for c in children]
        return items

    def makedirs(self, mode=0o777, exist_ok=False):
        return os.makedirs(self, mode=mode, exist_ok=exist_ok)

    @property
    def normcase(self):
        return os.path.normcase(self.absolute_path)

    def open(self, *args, **kwargs):
        return open(self, *args, **kwargs)

    @property
    def parent(self):
        if len(self._parts) == 1:
            return self

        return Path(self._parts[:-1], _case_correct=self._case_correct)

    def read(self, mode, **kwargs):
        '''
        Shortcut function for opening the file handle and reading data from it.
        '''
        with self.open(mode, **kwargs) as handle:
            return handle.read()

    def readlines(self, mode, **kwargs):
        '''
        Shortcut function for opening the file handle and reading lines from it.
        '''
        with self.open(mode, **kwargs) as handle:
            return handle.readlines()

    @property
    def relative_path(self):
        return self.relative_to(cwd())

    def relative_to(self, other, simple=False):
        if not isinstance(other, Path):
            other = Path(other)

        if self == other:
            return '.'

        if self in other:
            sub_parts = self._parts[len(other._parts):]
            relative = os.sep.join(part._name for part in sub_parts)
            if simple:
                return relative
            else:
                return f'.{os.sep}{relative}'

        common = common_path([self, other], fallback=None)

        if common is None:
            return self.absolute_path

        backsteps = other.depth - common.depth
        backsteps = os.sep.join('..' for x in range(backsteps))
        unique = [part._name for part in self._parts[common.depth:]]
        relative_path = os.path.join(backsteps, *unique)
        return relative_path

    def replace_extension(self, extension):
        '''
        Return a new Path that has the same basename as this one, but with a
        different extension. If this Path does not have any extension, it is
        added.
        '''
        extension = Extension(extension)
        base = os.path.splitext(self.basename)[0]

        if extension == '':
            return self.parent.with_child(base)

        return self.parent.with_child(base + extension.with_dot)

    @property
    def size(self):
        self.assert_exists()
        if self.is_file:
            return os.path.getsize(self)
        elif self.is_dir:
            return sum(file.size for file in self.walk() if file.is_file)

    @property
    def stat(self):
        return os.stat(self)

    def touch(self):
        '''
        Update the file's mtime if it exists, or create it.
        '''
        try:
            os.utime(self)
        except FileNotFoundError:
            self.open('a').close()

    def walk(self):
        '''
        Yield files and directories from this directory and subdirectories.
        '''
        directories = []

        entries = os.scandir(self)
        entries = sorted(entries, key=lambda e: os.path.normcase(e.name))
        for entry in entries:
            child = self.with_child(entry.name, _case_correct=self._case_correct)
            if entry.is_dir():
                directories.append(child)
            else:
                yield child

        for directory in directories:
            yield directory
            yield from directory.walk()

    def walk_directories(self):
        '''
        Yield directories from this directory and subdirectories.
        '''
        entries = os.scandir(self)
        entries = sorted(entries, key=lambda e: os.path.normcase(e.name))
        for entry in entries:
            if entry.is_dir():
                child = self.with_child(entry.name, _case_correct=self._case_correct)
                yield child
                yield from child.walk_directories()

    def walk_files(self):
        '''
        Yield files from this directory and subdirectories.
        '''
        # It would be nice to optimize this to not create Path objects for the
        # directories since we don't yield them, but it's cheaper to do many
        # directory.with_child(file) than it is to instantiate each file from
        # the path string anyway.
        return (item for item in self.walk() if item.is_file)

    def with_child(self, basename, **spawn_kwargs):
        if not isinstance(basename, str):
            raise TypeError(f'basename must be {str}, not {type(basename)}.')
        parts = (*self._parts, basename)
        return Path(parts, **spawn_kwargs)

    def write(self, mode, data, **kwargs):
        '''
        Shortcut function for opening the file handle and writing data into it.
        '''
        with self.open(mode, **kwargs) as handle:
            return handle.write(data)

class PathPart:
    '''
    The PathPart is any part after the drive. Each individual part must not
    contain path separators, those will be added when we join the tuple of
    parts back into a string.
    '''
    def __init__(self, name):
        if any(sep in name for sep in SEPS):
            raise ValueError('A path part cannot contain path separators.')
        self._name = name

def common_path(paths, fallback):
    '''
    Given a list of paths, determine the deepest path which all have in common.
    '''
    if isinstance(paths, (str, Path)):
        raise TypeError('`paths` must be a collection')

    paths = [Path(f) for f in paths]

    if len(paths) == 0:
        raise ValueError('Empty list')

    index = 0
    while True:
        try:
            this_level = set(os.path.normcase(path._parts[index]._name) for path in paths)
        except IndexError:
            break
        if len(this_level) > 1:
            break
        index += 1

    if index == 0:
        return fallback

    parts = paths[0]._parts[:index]
    return Path(parts)

def cwd():
    return Path(os.getcwd())

def get_path_casing(path):
    '''
    Take what is perhaps incorrectly cased input and get the path's actual
    casing according to the filesystem.

    Thank you:
    Ethan Furman http://stackoverflow.com/a/7133137/5430534
    xvorsx http://stackoverflow.com/a/14742779/5430534
    '''
    if not isinstance(path, Path):
        path = Path(path)

    # Nonexistent paths don't glob correctly. If the input is a nonexistent
    # subpath of an existing path, we have to glob the existing portion first,
    # and then attach the fake portion again at the end.
    input_path = path
    while not path.exists:
        parent = path.parent
        if path == parent:
            # We're stuck at a fake root.
            return input_path.absolute_path
        path = parent

    path = path.absolute_path

    (drive, subpath) = os.path.splitdrive(path)
    drive = drive.upper()
    subpath = subpath.lstrip(os.sep)

    pattern = [glob_patternize(piece) for piece in subpath.split(os.sep)]
    pattern = os.sep.join(pattern)
    pattern = drive + os.sep + pattern

    try:
        cased = _glob.glob(pattern)[0]
    except IndexError:
        return input_path.absolute_path

    imaginary_portion = input_path.absolute_path
    imaginary_portion = imaginary_portion[len(cased):]
    imaginary_portion = imaginary_portion.lstrip(os.sep)
    cased = os.path.join(cased, imaginary_portion)
    cased = cased.rstrip(os.sep)
    if os.sep not in cased:
        cased += os.sep
    return cased

def glob(pattern):
    '''
    Just like regular glob, except it returns Path objects instead of strings.

    If you want to recurse, consider using spinal.walk with glob_filenames
    instead.
    '''
    if pattern == '.':
        return [cwd()]

    elif pattern == '..':
        return [cwd().parent]

    (dirname, pattern) = os.path.split(pattern)
    return Path(dirname).glob(pattern)

def glob_directories(pattern):
    (dirname, pattern) = os.path.split(pattern)
    return Path(dirname).glob_directories(pattern)

def glob_files(pattern):
    (dirname, pattern) = os.path.split(pattern)
    return Path(dirname).glob_files(pattern)

def glob_many(patterns):
    '''
    Given many glob patterns, yield the results as a single generator.
    Saves you from having to write the nested loop.

    If you want to recurse, consider using spinal.walk(glob_filenames=[...])
    instead. The important difference between this function and spinal.walk is
    that spinal.walk starts from a root directory and looks for descendants
    that match the glob. This function can take patterns with no common root.
    '''
    for pattern in patterns:
        yield from glob(pattern)

def glob_many_directories(patterns):
    for pattern in patterns:
        yield from glob_directories(pattern)

def glob_many_files(patterns):
    for pattern in patterns:
        yield from glob_files(pattern)

def glob_patternize(piece):
    '''
    Create a pattern like "[u]ser" from "user". This forces glob to look up the
    correct path name, while guaranteeing that the only result will be
    the correct path.

    Special cases are:
        `!`
            because in glob syntax, [!x] tells glob to look for paths that
            don't contain "x", and [!] is invalid syntax.
        `[`, `]`
            because this starts a glob capture group

        so we pick the first non-special character to put in the brackets.
        If the path consists entirely of these special characters, then the
        casing doesn't need to be corrected anyway.
    '''
    piece = _glob.escape(piece)
    for character in piece:
        if character not in '![]':
            replacement = f'[{character}]'
            piece = piece.replace(character, replacement, 1)
            break
    return piece

def normalize_drive(name):
    if type(name) is Drive:
        return name
    return Drive(name)

def normalize_basename_glob(pattern):
    pattern = os.path.normpath(pattern)

    if os.sep in pattern:
        # If the user wants to glob names in a different path, they should
        # create a Pathclass for that directory first and do it normally.
        raise TypeError('glob pattern should not have path separators.')

    if not pattern:
        raise ValueError('glob pattern should not be empty.')

    return pattern

def normalize_pathpart(name):
    if type(name) is PathPart:
        return name
    return PathPart(name)

def normalize_sep(path) -> str:
    '''
    Normalize path separators as appropriate for the operating system.

    On Windows, forward slash / is replaced with backslash \\.

    Note: os.path.normpath also performs separator normalization, but it also
    eliminates leading ./ which you may want to keep in your string.
    '''
    if os.name == 'nt':
        path = path.replace('/', '\\')

    # On unix, backslashes are valid filename characters so we do not normalize
    # them to forward slash.

    return path

def system_root():
    return Path(os.sep)
