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

def set_level_by_argv(log, argv):
    basicConfig()
    argv = argv[:]

    if '--loud' in argv:
        log.setLevel(LOUD)
        argv.remove('--loud')
    elif '--debug' in argv:
        log.setLevel(DEBUG)
        argv.remove('--debug')
    elif '--quiet' in argv:
        log.setLevel(ERROR)
        argv.remove('--quiet')
    else:
        log.setLevel(INFO)

    return argv
