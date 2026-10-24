'''
operatornotify
==============

This module is designed to notify the program operator of important events
through the `notify` function. Most of the time, we are interested in being
notified when a program fails, but of course you can also notify when something
good happens, too.

By default, calling `notify` emits a log at the WARNING level, which is not very
interesting. But if you create your own file my_operatornotify.py somewhere on
your PYTHONPATH with a function notify(subject, body=''), all calls to
operatornotify.notify will go there. This module essentially self-monkeypatches
`notify` with your function.

For example, you might define your own file that sends emails, texts, or MQTT.
This allows the same calling code to behave differently on your dev / prod
environments, or other use cases you can imagine.

You can use different my_operatornotify files for different applications by
leveraging Python's sys.path order (cwd first, ...).

Alternatively, you can monkeypatch this module after importing it with a new
notify function in cases where you don't want to deal with import paths.

Some things to consider when authoring your my_operatornotify.notify function:
1. It is intended that both arguments are strings, but you may wish to call
   str() to always be safe.
2. If sending over a medium that doesn't distinguish subject / body
   (e.g. text message), consider concatenating subject+body.
3. Be careful that an exception during your notify function (network error, disk
   error) doesn't wind up making things worse!

This module should ONLY be called by application code, not library code.
Ideally, the application should provide a flag --operatornotify for the user
to opt-in to the use of operatornotify so that it does not surprise them.
The get_level_by_argv function should handle this opt-in for you.

If your application already uses the logging module, consider these options:
- add an instance of operatornotify.LogHandler to your logger,
- wrap your function call in a operatornotify.LogHandlerContext, or
- add @operatornotify.main_decorator to your main function.

You can also run this file on the command line to pipe the output of another
program to notify:

> some_process && operatornotify --subject success || operatornotify --subject fail
> some_process 2>&1 | operatornotify --subject "Results of some_process" --body !i
'''
import argparse
import contextlib
import functools
import io
import sys
import traceback

from voussoirkit import betterhelp
from voussoirkit import dotdict
from voussoirkit import pipeable
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'operatornotify')

BETTERHELP_EPILOGUE = '''
This program uses voussoirkit.operatornotify to allow the program operator to
receive messages about important events. See operatornotify.py's docstring to
learn how to create your own my_operatornotify file. Then, you can call this
program with the following arguments:

--operatornotify
    Opts in to notifications and will capture logging at the WARNING level.

--operatornotify-level X
    Opts in to notifications and will capture logging at level X, where X is
    e.g. debug, info, warning, error, critical.
    The program may choose to send notifications directly instead of using the
    logging stack. This option will not affect those.

--operatornotify-subject X
    Overrides the application's default subject line. Also implicitly opts in to
    logging at the WARNING level if --operatornotify-level isn't provided.
'''

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
    This handler makes it easy to integrate operatornotify into your application
    that already uses the logging module.

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

            If you are writing a long-running process / daemon where infrequent
            errors are being notified, you might want this True. If you're
            writing a command line application where all the results are sent
            at the end, you might want this False.
        '''
        self.subject = subject
        self.log_buffer = io.StringIO()
        self.notify_every_line = notify_every_line
        super().__init__(stream=self.log_buffer)

    def emit(self, record):
        # The StreamHandler emit will write the line into the stringio buffer.
        super().emit(record)
        if self.notify_every_line:
            self.notify()

    def notify(self):
        '''
        Send all of the logged contents to notify, then reset the buffer.
        '''
        text = self.log_buffer.getvalue()

        if not text:
            return

        try:
            notify(subject=self.subject, body=text)
        except Exception as exc:
            # Normally I'd put this into log.warning or log.error, but then we
            # might get stuck in an infinite loop! Not sure what's best.
            traceback.print_exc()
        else:
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
    def __init__(self, log, handler):
        '''
        The handler will be added to the logger at the beginning of the context
        and removed at the end. All of the log lines captured during the context
        will be sent to notify.

        log:
            Your logger from logging.getLogger
        '''
        self.log = log
        self.handler = handler

    def __enter__(self):
        self.log.addHandler(self.handler)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type not in (None, KeyboardInterrupt):
            exc_text = traceback.format_exception(exc_type, exc_value, exc_traceback)
            exc_text = ''.join(exc_text)
            exc_text = '\n'.join([
                'The context was killed by the following exception:',
                f'{exc_text}'
            ])
            # Intentionally using module's log, not self.log because I think
            # it should be clear who emitted the message, and the caller can
            # mute this module if they want to.
            log.error(exc_text)

        self.handler.notify()
        self.log.removeHandler(self.handler)

def main_decorator(subject, **log_handler_kwargs):
    '''
    Add this decorator to your application's main function to automatically
    wrap it in a LogHandlerContext, and enable the commandline options.

    @operatornotify.main_decorator(subject='myprogram.py')
    def main(argv):
        ...

    if __name__ == '__main__':
        raise SystemExit(main(sys.argv[1:]))

    This will:
    1. Allow the user to opt into operatornotify by --operatornotify or
       --operatornotify-level X.
    2. Remove those args from argv so your argparse doesn't know the difference.
    3. Wrap main call with LogHandlerContext.

    Your additional kwargs will go to the log handler, so you can do:

    @operatornotify.main_decorator(subject='myprogram.py', log_every_line=True)

    This is done as an argument to the decorator rather than a commandline
    argument because normally the nature of the application dictates this
    decision. For example, a webserver or other daemon probably wants to notify
    every line, but a quick commandline utility probably doesn't. It seems
    unlikely that the user would want to specify this.
    '''
    betterhelp.HELPTEXT_EPILOGUES.add(BETTERHELP_EPILOGUE)
    def wrapper(main):
        @functools.wraps(main)
        def wrapped(argv, *main_args, **main_kwargs):
            parsed = parse_argv(argv)
            argv = parsed.argv

            if parsed.level is None:
                return main(argv, *main_args, **main_kwargs)

            handler = LogHandler(parsed.subject or subject, **log_handler_kwargs)
            handler.setLevel(parsed.level)
            handler.setFormatter(vlogging.make_formatter(parsed.level))
            vlogging.root.addHandler(handler)

            context = LogHandlerContext(log=vlogging.root, handler=handler)
            with context:
                return main(argv, *main_args, **main_kwargs)
        return wrapped
    return wrapper

def parse_argv(argv):
    '''
    Parse argv looking for operatornotify arguments.
    Please see the BETTERHELP_EPILOGUE.

    Returns a dotdict with these keys:
    - argv, which has all --operatornotify* arguments removed.
    - level, either an integer log level or None. Even if you are not attaching
      operatornotify to your logger, you can still use this value to make
      decisions about when/what to notify. None means did not opt-in.
    - subject, either a string to override the application's subject or None.

    Raises ValueError if --operatornotify-level X is not a recognized level.
    '''
    level = None
    subject = None
    new_argv = []
    index = 0
    while index < len(argv):
        arg = argv[index]

        if arg in {'--operatornotify_level', '--operatornotify-level'}:
            level = argv[index + 1]
            index += 1

        elif arg in {'--operatornotify_subject', '--operatornotify-subject'}:
            if level is None:
                level = vlogging.WARNING
            subject = argv[index + 1]
            index += 1

        elif arg == '--operatornotify':
            if level is None:
                level = vlogging.WARNING

        else:
            new_argv.append(arg)

        index += 1

    if isinstance(level, str):
        try:
            level = int(level)
        except ValueError:
            level = vlogging.get_level_by_name(level)

    return dotdict.DotDict(
        argv=new_argv,
        level=level,
        subject=subject,
    )

def operatornotify_argparse(args):
    notify(
        subject=pipeable.input(args.subject, split_lines=False).strip(),
        body=pipeable.input(args.body or '', split_lines=False),
    )
    return 0

@vlogging.main_decorator(log=log)
def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--subject',
        required=True,
        help='''
        A string. Uses pipeable to support !c clipboard, !i stdin.
        ''',
    )
    parser.add_argument(
        '--body',
        help='''
        A string. Uses pipeable to support !c clipboard, !i stdin.
        ''',
    )
    parser.set_defaults(func=operatornotify_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
