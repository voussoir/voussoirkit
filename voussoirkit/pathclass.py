import glob
import os
import re

from voussoirkit import winglob


class PathclassException(Exception):
    pass

class Exists(PathclassException):
    pass

class NotExists(PathclassException):
    pass

class NotDirectory(PathclassException):
    pass

class NotFile(PathclassException):
    pass


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
    '''
    I started to use pathlib.Path, but it was too much of a pain.
    '''
    def __init__(self, path, force_sep=None):
        self.force_sep = force_sep
        self.sep = force_sep or os.sep

        if isinstance(path, Path):
            self.absolute_path = path.absolute_path
        else:
            path = path.strip()
            if re.search('^[A-Za-z]:$', path):
                # Bare Windows drive letter.
                path += self.sep
            path = normalize_sep(path)
            path = os.path.normpath(path)
            path = os.path.abspath(path)
            self.absolute_path = path

        self.absolute_path = normalize_sep(self.absolute_path, self.sep)

    def __contains__(self, other):
        other = self.spawn(other)

        self_norm = self.normcase
        if not self_norm.endswith(self.sep):
            self_norm += self.sep
        return other.normcase.startswith(self_norm)

    def __eq__(self, other):
        if not hasattr(other, 'absolute_path'):
            return False
        # Compare by normcase so that Windows's case-insensitive filenames
        # behave correctly.
        return self.normcase == other.normcase

    def __hash__(self):
        return hash(self.normcase)

    def __lt__(self, other):
        # Sort by normcase so that Windows's case-insensitive filenames sort
        # alphabetically regardless of case.
        return self.normcase < other.normcase

    def __repr__(self):
        return '{c}({path})'.format(c=self.__class__.__name__, path=repr(self.absolute_path))

    def assert_exists(self):
        if not self.exists:
            raise NotExists(self)

    def assert_not_exists(self):
        if self.exists:
            raise Exists(self)

    def assert_is_file(self):
        if not self.is_file:
            raise NotFile(self)

    def assert_is_directory(self):
        if not self.is_dir:
            raise NotDirectory(self)

    def add_extension(self, extension):
        extension = Extension(extension)
        if extension == '':
            return self
        return self.parent.with_child(self.basename + extension.with_dot)

    @property
    def basename(self):
        return os.path.basename(self.absolute_path)

    def correct_case(self):
        self.absolute_path = get_path_casing(self.absolute_path)
        self.absolute_path = self.absolute_path.replace('/', self.sep).replace('\\', self.sep)
        return self.absolute_path

    @property
    def depth(self):
        return len(self.absolute_path.rstrip(self.sep).split(self.sep))

    @property
    def dot_extension(self):
        return self.extension.with_dot

    @property
    def drive(self):
        return os.path.splitdrive(self.absolute_path)[0]

    @property
    def exists(self):
        return os.path.exists(self.absolute_path)

    @property
    def extension(self):
        return Extension(os.path.splitext(self.absolute_path)[1])

    def glob(self, pattern):
        if '/' in pattern or '\\' in pattern:
            # If the user wants to glob names in a different path, they should
            # create a Pathclass for that directory first and do it normally.
            raise TypeError('glob pattern should not have path separators')
        pattern = self.with_child(pattern)
        children = winglob.glob(pattern.absolute_path)
        children = [self.with_child(child) for child in children]
        return children

    @property
    def is_dir(self):
        return os.path.isdir(self.absolute_path)

    @property
    def is_file(self):
        return os.path.isfile(self.absolute_path)

    @property
    def is_link(self):
        return os.path.islink(self.absolute_path)

    def join(self, subpath):
        if not isinstance(subpath, str):
            raise TypeError('subpath must be a string')
        path = os.path.join(self.absolute_path, subpath)
        return self.spawn(path)

    def listdir(self):
        children = os.listdir(self.absolute_path)
        children = [self.with_child(child) for child in children]
        return children

    @property
    def normcase(self):
        norm = os.path.normcase(self.absolute_path)
        norm = norm.replace('/', self.sep).replace('\\', self.sep)
        return norm

    @property
    def parent(self):
        parent = os.path.dirname(self.absolute_path)
        return self.spawn(parent)

    @property
    def relative_path(self):
        return self.relative_to(os.getcwd())

    def relative_to(self, other, simple=False):
        other = self.spawn(other)

        if self == other:
            return '.'

        self.correct_case()
        other.correct_case()

        if self in other:
            relative = self.absolute_path
            relative = relative.replace(other.absolute_path, '', 1)
            relative = relative.lstrip(self.sep)
            if not simple:
                relative = '.' + self.sep + relative
            return relative

        common = common_path([other.absolute_path, self.absolute_path], fallback=None)

        if common is None:
            return self.absolute_path

        common = self.spawn(common)
        backsteps = other.depth - common.depth
        backsteps = self.sep.join('..' for x in range(backsteps))
        common = common.absolute_path
        if not common.endswith(self.sep):
            common += self.sep
        unique = self.absolute_path.replace(common, '', 1)
        relative_path = os.path.join(backsteps, unique)
        relative_path = relative_path.replace('/', self.sep).replace('\\', self.sep)
        return relative_path

    def replace_extension(self, extension):
        extension = Extension(extension)
        base = os.path.splitext(self.basename)[0]

        if extension == '':
            return self.parent.with_child(base)

        return self.parent.with_child(base + extension.with_dot)

    @property
    def size(self):
        self.assert_exists()
        if self.is_file:
            return os.path.getsize(self.absolute_path)
        elif self.is_dir:
            return sum(file.size for file in self.walk() if file.is_file)

    def spawn(self, path):
        return self.__class__(path, force_sep=self.force_sep)

    @property
    def stat(self):
        return os.stat(self.absolute_path)

    def touch(self):
        try:
            os.utime(self.absolute_path)
        except FileNotFoundError:
            open(self.absolute_path, 'a').close()

    def walk(self):
        directories = []
        for child in self.listdir():
            if child.is_dir:
                directories.append(child)
            else:
                yield child

        for directory in directories:
            yield directory
            yield from directory.walk()

    def with_child(self, basename):
        return self.join(os.path.basename(basename))


def common_path(paths, fallback):
    '''
    Given a list of file paths, determine the deepest path which all
    have in common.
    '''
    if isinstance(paths, (str, Path)):
        raise TypeError('`paths` must be a collection')

    paths = [Path(f) for f in paths]

    if len(paths) == 0:
        raise ValueError('Empty list')

    if hasattr(paths, 'pop'):
        model = paths.pop()
    else:
        model = paths[0]
        paths = paths[1:]

    while True:
        if all(f in model for f in paths):
            return model
        parent = model.parent
        if parent == model:
            # We just processed the root, and now we're stuck at the root.
            # Which means there was no common path.
            return fallback
        model = parent

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
        cased = glob.glob(pattern)[0]
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

def glob_patternize(piece):
    '''
    Create a pattern like "[u]ser" from "user", forcing glob to look up the
    correct path name, while guaranteeing that the only result will be the correct path.

    Special cases are:
        `!`
            because in glob syntax, [!x] tells glob to look for paths that don't contain
            "x", and [!] is invalid syntax.
        `[`, `]`
            because this starts a glob capture group

        so we pick the first non-special character to put in the brackets.
        If the path consists entirely of these special characters, then the
        casing doesn't need to be corrected anyway.
    '''
    piece = glob.escape(piece)
    for character in piece:
        if character not in '![]':
            replacement = f'[{character}]'
            piece = piece.replace(character, replacement, 1)
            break
    return piece

def normalize_sep(path, sep=None):
    sep = sep or os.sep
    path = path.replace('/', sep)
    path = path.replace('\\', sep)

    return path

def system_root():
    return os.path.abspath(os.sep)
