'''
vlogging
========

Hey, what's up guys, it's voussoirkit back with another awesome module for you.
This module forwards everything from logging, with the addition of levels LOUD
and SILENT, and all loggers from getLogger are given the `loud` method.

Don't forget to like, comment, and subscribe.
'''
import functools
from logging import *
import sys

_getLogger = getLogger

BETTERHELP_EPILOGUE = '''
This program uses voussoirkit.vlogging to make logging controls accessible via
command line arguments. You can add the following arguments to change the
logging level:

--loud
--debug
--warning
--quiet
--silent
'''

# Python gives the root logger a level of WARNING. The problem is that prevents
# any handlers you add to it from receiving lower level messages. WARNING might
# be fine for the stderr handler, but you might like to have a log file
# containing everything including info and debug.
# I find that logging works best if the root logger itself doesn't have a level
# and the handlers can choose what they want.
root = getLogger()
root.setLevel(NOTSET)

LOUD = 1
SILENT = 99999999999

ARGV_LEVEL = NOTSET
_did_earlybird = False

def add_loud(log):
    '''
    Add the `loud` method to the given logger.
    '''
    def loud(self, message, *args, **kwargs):
        if self.isEnabledFor(LOUD):
            self._log(LOUD, message, args, **kwargs)

    addLevelName(LOUD, 'LOUD')
    log.loud = loud.__get__(log, log.__class__)

def add_root_handler(level):
    handler = StreamHandler()
    datefmt = '%Y-%m-%dT%H:%M:%S'
    if level <= LOUD:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}.{funcName}.{lineno}:{message}', style='{', datefmt=datefmt)
    elif level <= DEBUG:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}.{funcName}:{message}', style='{', datefmt=datefmt)
    else:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}:{message}', style='{', datefmt=datefmt)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root.addHandler(handler)
    return handler

def basic_config(level):
    '''
    This adds a handler with the given level to the root logger, but only
    if it has no handlers yet.
    '''
    if root.handlers:
        return

    add_root_handler(level)

def basic_config_by_argv(argv):
    '''
    This function does basic_config with a level set by the flags in argv, then
    returns the rest of argv which you can pass to your argparser.
    '''
    (level, argv) = get_level_by_argv(argv)
    basic_config(level)
    return argv

def earlybird_config():
    '''
    This function will call basic_config_by_argv and **overwrite** sys.argv with
    the remaining arguments. You can import vlogging and call this function
    before doing anything else to ensure that logging is ready from the very
    beginning.

    This can be used if waiting until main runs (@main_decorator) is too
    late because you have log statements that run while your modules / imports
    are loading.

    However, this might have the downside of making your program more difficult
    to debug because sys.argv is permanently altered.
    '''
    global _did_earlybird
    sys.argv = basic_config_by_argv(sys.argv)
    _did_earlybird = True

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

    def tryremove(lst, item):
        try:
            lst.remove(item)
            return True
        except ValueError:
            return False

    if tryremove(argv, '--loud'):
        level = LOUD
    elif tryremove(argv, '--debug'):
        level = DEBUG
    elif tryremove(argv, '--warning'):
        level = WARNING
    elif tryremove(argv, '--quiet'):
        level = ERROR
    elif tryremove(argv, '--silent'):
        level = SILENT
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

def get_logger(name=None, main_fallback=None):
    '''
    Normally it is best practice to use get_logger(__name__), but when running
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

getLogger = get_logger

def main_decorator(main):
    '''
    Add this decorator to your application's main function to automatically
    set the main log handler level by the arguments in argv. This allows you
    to use --debug, --quiet, etc. on the command line without making any
    changes to your argparser.
    '''
    from voussoirkit import betterhelp
    betterhelp.HELPTEXT_EPILOGUES.add(BETTERHELP_EPILOGUE)
    @functools.wraps(main)
    def wrapped(argv, *args, **kwargs):
        global ARGV_LEVEL
        # The reason we don't call basic_config is that another module may have
        # attached a root handler for another purpose.
        # However we do check _did_earlybird so that we don't get double
        # handlers from this module.
        if not _did_earlybird:
            (level, argv) = get_level_by_argv(argv)
            ARGV_LEVEL = level
            add_root_handler(level)
        return main(argv, *args, **kwargs)
    return wrapped
