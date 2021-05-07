'''
operatornotify
==============

This module is designed to notify the program operator of important events.
By default, it just logs at the WARNING level, but if you create your own
file my_operatornotify.py somewhere on your PYTHONPATH with a function
notify(subject, body=''), all calls to this module will go there.
For example, you might define your own file that sends emails, texts, or MQTT.
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

If your application already uses the logging module, consider adding an
instance of operatornotify.LogHandler to your logger, or wrapping your whole
main call in a LogHandlerContext.

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
import contextlib
import io
import sys
import traceback

from voussoirkit import betterhelp
from voussoirkit import pipeable
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'operatornotify')

####################################################################################################

def default_notify(subject, body=''):
    if body:
        log.warning('%s: %s', subject, body)
    else:
        log.warning(subject)

try:
    import my_operatornotify
    notify = my_operatornotify.notify
except ImportError:
    notify = default_notify

####################################################################################################

class LogHandler(vlogging.StreamHandler):
    '''
    This handler makes it easy to integrate operatornotify into your
    application that already uses the logging module.

    Create an instance of this class and add it to your logger. Use setLevel
    and other filtering tools to get messages of interest. You may choose to
    get notified for each log line individually, or buffer them and send them
    all together. When you are ready to send the buffered contents,
    call handler.notify().
    If no messages have been logged yet, handler.notify will do nothing.
    '''
    def __init__(self, subject, notify_every_line=False):
        '''
        subject:
            The subject string for all notify calls. The body will be the
            contents of logged messages.

        notify_every_line:
            If True, each log call will send a notification immediately.
            Otherwise, they are buffered until handler.notify is called.
        '''
        self.subject = subject
        self.log_buffer = io.StringIO()
        self.notify_every_line = notify_every_line
        super().__init__(stream=self.log_buffer)

    def __del__(self):
        # Remember that del is not guaranteed to execute, but this should help
        # out in cases where notify is never called.
        self.notify()

    def emit(self, record):
        super().emit(record)
        if self.notify_every_line:
            self.notify()

    def notify(self):
        '''
        Send all of the logged contents to notify, then reset the buffer.
        '''
        if self.log_buffer.getvalue():
            notify(subject=self.subject, body=self.log_buffer.getvalue())
            self.reset_buffer()

    def reset_buffer(self):
        self.log_buffer = io.StringIO()
        self.setStream(self.log_buffer)

class LogHandlerContext:
    '''
    This context manager captures all log lines that occur during the context,
    and also records any fatal exception that kills the context, then sends all
    of this to notify. This saves you from having to call handler.notify
    yourself, because it will occur when the context ends.
    '''
    def __init__(self, log, handler, log_exception=True):
        '''
        log:
            Your logger from logging.getLogger

        handler:
            Your operatornotify.LogHandler

        log_exception:
            If the context is killed by an exception, include the traceback at
            the bottom of the notification.
        '''
        self.log = log
        self.handler = handler
        self.log_exception = log_exception

    def __enter__(self):
        self.log.addHandler(self.handler)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.log_exception and exc_type not in (None, KeyboardInterrupt):
            exc_text = traceback.format_exception(exc_type, exc_value, exc_traceback)
            exc_text = ''.join(exc_text)
            exc_text = f'\n\n{exc_text}\n'
            self.handler.log_buffer.write(exc_text)

        self.handler.notify()
        self.log.removeHandler(self.handler)

def main_log_context(argv, subject, *args, **kwargs):
    '''
    This function is for accelerating the common use case of adding
    operatornotify to a commandline application's existing logger.
    The goals are:

    1. Opt into operatornotify by --operatornotify, or return a nullcontext.
    2. Set handler's level by --operatornotify-level X.
    3. Remove those args from argv so your argparse doesn't know the difference.
    4. Add handler to the root logger.
    5. Provide a context manager with which you'll wrap your main function.
    6. Operatornotify captures all log messages and any fatal exception
        that kills your main function.
    7. Results are sent at the end of runtime.

    Returns (context, argv) where argv can go into your argparse and context
    can wrap your main call.
    '''
    # This serves the purpose of normalizing the argument, but also creating a
    # duplicate list so we are not altering sys.argv.
    # Do not modiy this code without considering both effects.
    argv = ['--operatornotify-level' if arg == '--operatornotify_level' else arg for arg in argv]

    if '--operatornotify' in argv:
        argv.remove('--operatornotify')
    else:
        return (contextlib.nullcontext(), argv)

    if '--operatornotify-level' in argv:
        level = argv.pop(argv.index('--operatornotify-level') + 1)
        try:
            level = int(level)
        except ValueError:
            pass
        argv.remove('--operatornotify-level')
    else:
        level = vlogging.WARNING

    level = vlogging.get_level_by_name(level)

    log = vlogging.getLogger()
    handler = LogHandler(subject, *args, **kwargs)
    handler.setLevel(level)
    handler.setFormatter(vlogging.Formatter('{levelname}:{name}:{message}', style='{'))
    context = LogHandlerContext(log, handler, log_exception=True)
    return (context, argv)

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
