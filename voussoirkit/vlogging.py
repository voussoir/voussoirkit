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
import time
import traceback

from voussoirkit import dotdict
from voussoirkit import pathclass

_getLogger = getLogger

BETTERHELP_EPILOGUE = '''
This program uses voussoirkit.vlogging to make logging controls accessible via
command line arguments. You can add the following arguments to change the
logging level of stderr:

--loud
--debug
--warning
--quiet
--silent

You can add the following arguments to direct a log stream towards a file:

--logfile-folder (or --logfile-directory)
--logfile-level
'''

# Python gives the root logger a level of WARNING. The problem is that prevents
# any handlers you add to it from receiving lower level messages. WARNING might
# be fine for the stderr handler, but you might like to have a log file
# containing everything including info and debug.
# I find that logging works best if the root logger itself doesn't have a level
# and the handlers can choose what they want.
root = getLogger()
root.setLevel(NOTSET)

vlogging_log = getLogger(__name__)

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

def basic_config(level):
    '''
    This adds a handler with the given level to the root logger, but only
    if it has no handlers yet.
    '''
    if root.handlers:
        return

    handler = StreamHandler()
    handler.setFormatter(make_formatter(level))
    handler.setLevel(level)
    root.addHandler(handler)

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

def main_decorator(*, log, log_return_level=(INFO, WARNING)):
    '''
    Add this decorator to your application's main function to automatically
    set the main log handler level by the arguments in argv. This allows you
    to use --debug, --quiet, etc. on the command line without making any
    changes to your argparser.

    log_return_level is a 2-tuple being the level for logging good return
    statuses and the level for logging bad return statuses. Good statuses are
    0, and bad statuses are anything else. This is decided by the application
    rather than command-line arguments. By default, good statuses are logged to
    INFO and bad statuses are logged to WARNING. If you are also using
    operatornotify, this is a good default because the user probably wants
    to get notified when the program fails, but not when it is successful,
    unless they pass --operatornotify-level INFO.

    If you don't want that at all, you can pass log_return_level=None.
    '''
    from voussoirkit import betterhelp
    betterhelp.HELPTEXT_EPILOGUES.add(BETTERHELP_EPILOGUE)

    if log_return_level is not None:
        (log_return_level_good, log_return_level_bad) = log_return_level

    def wrapper(main):
        @functools.wraps(main)
        def wrapped(argv, *main_args, **main_kwargs):
            global ARGV_LEVEL
            # The reason we don't call basic_config is that another module may have
            # attached a root handler for another purpose.
            # However we do check _did_earlybird so that we don't get double
            # handlers from this module.
            parsed = parse_argv(argv)
            if not _did_earlybird:
                ARGV_LEVEL = parsed.level
                handler = StreamHandler()
                handler.setFormatter(make_formatter(parsed.level))
                handler.setLevel(parsed.level)
                root.addHandler(handler)

            if parsed.logfile_folder:
                parsed.logfile_folder = pathclass.Path(parsed.logfile_folder)
                parsed.logfile_folder.makedirs(exist_ok=True)

                log_file_name = time.strftime(f'{log.name} %Y-%m-%d-%H-%M-%S.log')
                log_file = parsed.logfile_folder.with_child(log_file_name)
                log_file_handler = FileHandler(log_file.absolute_path, delay=True)
                log_file_handler.setFormatter(make_formatter(level=parsed.logfile_level))
                log_file_handler.setLevel(parsed.logfile_level)

                root.addHandler(log_file_handler)

            try:
                status = main(parsed.argv, *main_args, **main_kwargs)
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                exc_text = traceback.format_exception(exc)
                exc_text = ''.join(exc_text)
                exc_text = '\n'.join([
                    'The program was killed by the following exception:',
                    f'{exc_text}'
                ])
                # Intentionally using vlogging's log, not application's log
                # because I think it should be clear who emitted the message,
                # and the caller can mute this module if they want to.
                vlogging_log.error(exc_text)
                raise

            if log_return_level is None:
                pass
            elif status == 0:
                vlogging_log.log(log_return_level_good, 'Program finished, returned %s.', status)
            else:
                vlogging_log.log(log_return_level_bad, 'Program finished, returned %s.', status)

            return status
        return wrapped
    return wrapper

def make_formatter(level):
    datefmt = '%Y-%m-%dT%H:%M:%S'
    if level <= LOUD:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}.{funcName}.{lineno}:{message}', style='{', datefmt=datefmt)
    elif level <= DEBUG:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}.{funcName}:{message}', style='{', datefmt=datefmt)
    else:
        formatter = Formatter('[{asctime}.{msecs:03.0f}] {levelname}:{name}:{message}', style='{', datefmt=datefmt)
    formatter.default_msec_format = '%s.%03d'
    return formatter

def parse_argv(argv):
    '''
    Parse argv looking for vlogging arguments, and return the rest of argv with
    those removed.
    Please see the BETTERHELP_EPILOGUE.

    Returns a dotdict with these keys:
    - argv, which has all vlogging arguments removed.
    - level,
    - logfile_folder
    - logfile_level
    '''

    parsed = dotdict.DotDict(
        argv=[],
        level=None,
        logfile_folder=None,
        logfile_level=None,
    )
    index = 0
    while index < len(argv):
        arg = argv[index]

        if arg == '--loud':
            parsed.level = LOUD
        elif arg == '--debug':
            parsed.level = DEBUG
        elif arg == '--info':
            parsed.level = INFO
        elif arg == '--warning':
            parsed.level = WARNING
        elif arg == '--quiet':
            parsed.level = ERROR
        elif arg == '--silent':
            parsed.level = SILENT

        elif arg in {'--logfile_level', '--logfile-level'}:
            parsed.logfile_level = get_level_by_name(argv[index + 1])
            index += 1

        elif arg in {'--logfile_folder', '--logfile-folder', '--logfile_directory', '--logfile-directory'}:
            if parsed.logfile_level is None:
                parsed.logfile_level = INFO
            parsed.logfile_folder = argv[index + 1]
            index += 1

        else:
            parsed.argv.append(arg)

        index += 1

    if parsed.level is None:
        parsed.level = INFO

    if parsed.logfile_level is None:
        parsed.logfile_level = INFO

    return parsed
