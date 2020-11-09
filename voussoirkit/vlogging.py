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
    basicConfig()

    (level, argv) = get_level_by_argv(argv)
    log.setLevel(level)

    return argv
