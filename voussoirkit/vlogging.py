'''
vlogging
========

Hey, what's up guys, it's voussoirkit back with another awesome module for you.
This module forwards everything from logging, with the addition of levels LOUD
and SILENT, and all loggers from getLogger are given the `loud` method.

Don't forget to like, comment, and subscribe.
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
    '''
    Add the `loud` method to the given logger.
    '''
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
    --warning: WARNING
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
    elif '--warning' in argv:
        level = WARNING
        argv.remove('--warning')
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
        'SILENT': SILENT,
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

def main_decorator(main):
    '''
    Add this decorator to your application's main function to automatically
    set the main log handler level by the arguments in argv. This allows you
    to use --debug, --quiet, etc. on the command line without making any
    changes to your argparser.
    '''
    def wrapped(argv):
        argv = main_level_by_argv(argv)
        return main(argv)
    return wrapped

def main_level_by_argv(argv):
    '''
    This function puts a handler on the root logger with a level set by the
    flags in argv, then returns the rest of argv which you can pass to
    your argparser.
    '''
    (level, argv) = get_level_by_argv(argv)

    # Previously I was using basicConfig to prepare the handlers and then
    # setting root.setLevel, but the problem is that prevents any other
    # handlers on the root from receiving messages at a lower level.
    # It works best if the logger itself doesn't have a level and the handlers
    # can choose what they want.
    root = getLogger()
    root.setLevel(NOTSET)

    handler = StreamHandler()
    handler.setFormatter(Formatter('{levelname}:{name}:{message}', style='{'))
    handler.setLevel(level)
    root.addHandler(handler)

    return argv
