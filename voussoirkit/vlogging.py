from logging import *

_getLogger = getLogger

LOUD = 1

def getLogger(*args, **kwargs):
    log = _getLogger(*args, **kwargs)
    add_loud(log)
    return log

def add_loud(log):
    addLevelName(LOUD, 'LOUD')
    log.loud = lambda *args, **kwargs: log.log(LOUD, *args, **kwargs)

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
    --silent: 99999999999
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
        level = 99999999999
        argv.remove('--silent')
    else:
        level = INFO

    return (level, argv)

def set_level_by_argv(log, argv):
    '''
    This function is helpful for single-file scripts where you instantiate the
    logger in the global scope, and use this function to set its level
    according to the "--debug" flags in argv, then pass the rest of argv to
    your argparser.
    '''
    basicConfig()

    (level, argv) = get_level_by_argv(argv)
    log.setLevel(level)

    return argv
