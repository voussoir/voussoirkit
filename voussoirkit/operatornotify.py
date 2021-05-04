'''
operatornotify
==============

This module is designed to notify the program operator of important events.
By default, it just logs at the WARNING level, but if you create your own
file my_operatornotify.py somewhere on your PYTHONPATH with a function
notify(subject, body=''), all calls to this module will go there.
For example, you might define your own file that sends emails or texts.
This allows the same calling code to behave differently on your dev / prod
environments, or other use cases you can imagine.
You can use different my_operatornotify files for different applications by
leveraging Python's sys.path order (cwd first, ...).

Alternatively, you can monkeypatch this module after importing it with a new
notify function in cases where you don't want to deal with import paths.

Authoring your my_operatornotify.notify function:
1. It is intended that both arguments are strings, but you may wish to call
   str() to always be safe.
2. If sending over a medium that doesn't distinguish subject / body
   (e.g. text message), consider concatenating subject+body.

This module should ONLY be called by application code, not library code.
Ideally, the application should provide a flag --operatornotify for the user
to opt-in to the use of operatornotify so that it does not surprise them.

Commandline usage:

> operatornotify --subject XXX [--body XXX]

--subject:
    A string. Uses pipeable to support !c clipboard, !i stdin.
    Required.

--body:
    A string. Uses pipeable to support !c clipboard, !i stdin.

Examples:
> some_process && operatornotify --subject success || operatornotify --subject fail
> some_process | operatornotify --subject "Results of some_process" --body !i 2>&1
'''
import argparse
import sys

from voussoirkit import betterhelp
from voussoirkit import pipeable
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'operatornotify')

try:
    import my_operatornotify
    notify = my_operatornotify.notify
except ImportError:
    def notify(subject, body=''):
        if body:
            log.warning('%s: %s', subject, body)
        else:
            log.warning(subject)

def operatornotify_argparse(args):
    notify(
        subject='\n'.join(pipeable.input(args.subject)),
        body='\n'.join(pipeable.input(args.body)),
    )

def main(argv):
    argv = vlogging.set_level_by_argv(log, argv)

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--subject', required=True)
    parser.add_argument('--body', default='')
    parser.set_defaults(func=operatornotify_argparse)

    return betterhelp.single_main(argv, parser, __doc__)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
