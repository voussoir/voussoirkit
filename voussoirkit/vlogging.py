'''
This module forwards everything from logging, with the addition of a level
LOUD=1 and all loggers are given the `loud` method.
'''
from logging import *

_getLogger = getLogger

LOUD = 1
SILENT = 99999999999

def getLogger(name=None, main_fallback=None):
    '''
    Normally it is best practice to use getLogger(__name__), but when running
    a script directly you'll see "__main__" in the output, which I think is
    ugly and unexpected for anyone who doesn't know what's going on behind
    the scenes. But hardcoding your logger name is not good either.
    So, main_fallback is used to present your preferred name in case of main.
    '''
    if name == '__main__' and main_fallback is not None:
        name = main_fallback
    log = _getLogger(name)
    add_loud(log)
    return log

def add_loud(log):
    def loud(self, message, *args, **kwargs):
        if self.isEnabledFor(LOUD):
            self._log(LOUD, message, args, **kwargs)

    addLevelName(LOUD, 'LOUD')
    log.loud = loud.__get__(log, log.__class__)

def get_level_by_argv(argv):
    '''
    If any of the following arguments are present in argv, return the
    corresponding log level along with a new copy of argv that has had the
    argument string removed.

    Since we are removing the argument, your argparser should not have options
    with these same names.

    --loud: LOUD
    --debug: DEBUG
    --quiet: ERROR
    --silent: SILENT
    none of the above: INFO
    '''
    argv = argv[:]

    if '--loud' in argv:
        level = LOUD
        argv.remove('--loud')
    elif '--debug' in argv:
        level = DEBUG
        argv.remove('--debug')
    elif '--quiet' in argv:
        level = ERROR
        argv.remove('--quiet')
    elif '--silent' in argv:
        level = SILENT
        argv.remove('--silent')
    else:
        level = INFO

    return (level, argv)

def get_level_by_name(name):
    '''
    The logging module maintains a private variable _nameToLevel but does not
    have an official public function for querying it. There is getLevelName,
    but that function never fails an input, it just returns it back to you as
    "Level X" for any number X, or indeed any hashable type! The return value
    of getLevelName isn't accepted by setLevel since setLevel does not parse
    "Level X" strings, though it does accept exact matches by registered
    level names.

    Consider this function your alternative, for querying levels by name and
    getting an integer you can give to setLevel.
    '''
    if isinstance(name, int):
        return name

    if not isinstance(name, str):
        raise TypeError(f'name should be str, not {type(name)}.')

    name = name.upper()

    levels = {
        'CRITICAL': CRITICAL,
        'FATAL': FATAL,
        'ERROR': ERROR,
        'WARN': WARNING,
        'WARNING': WARNING,
        'INFO': INFO,
        'DEBUG': DEBUG,
        'LOUD': LOUD,
        'NOTSET': NOTSET,
    }

    value = levels.get(name)

    if value is None:
        raise ValueError(f'{name} is not a known level.')

    return value

def main_level_by_argv(argv):
    '''
    This function calls basicConfig to initialize the root logger, sets the
    root log's level by the flags in argv, then returns the rest of argv which
    you can pass to your argparser.
    '''
    basicConfig()

    (level, argv) = get_level_by_argv(argv)
    getLogger().setLevel(level)

    return argv

def set_level_by_argv(log, argv):
    '''
    This function sets the log's level by the flags in argv, then returns the
    rest of argv which you can pass to your argparser.
    '''
    (level, argv) = get_level_by_argv(argv)
    log.setLevel(level)

    return argv
