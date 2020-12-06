# import pyperclip moved to stay lazy.
import os
import sys

CLIPBOARD_STRINGS = ['!c', '!clip', '!clipboard']
INPUT_STRINGS = ['!i', '!in', '!input', '!stdin']
EOF = '\x1a'

# In pythonw, stdin and stdout are None.
IN_PIPE = (sys.stdin is not None) and (not sys.stdin.isatty())
OUT_PIPE = (sys.stdout is not None) and (not sys.stdout.isatty())

class PipeableException(Exception):
    pass

class NoArguments(PipeableException):
    pass

def ctrlc_return1(function):
    '''
    Apply this decorator to your argparse gateways, and if the user presses
    ctrl+c then the gateway will return 1 as its status code without the
    stacktrace appearing.

    This helps me avoid wrapping the entire function in a try-except block.

    Don't use this if you need to perform some other kind of cleanup on ctrl+c.
    '''
    def wrapped(*args, **kwargs):
        try:
            function(*args, **kwargs)
        except KeyboardInterrupt:
            return 1
    return wrapped

def _multi_line_input(prompt=None):
    if prompt is not None and not IN_PIPE:
        sys.stderr.write(prompt)
        sys.stderr.flush()

    while True:
        line = sys.stdin.readline()
        parts = line.split(EOF)
        line = parts[0]
        has_eof = len(parts) > 1

        # Note that just by hitting enter you always get \n, so this does NOT
        # mean that input finishes by submitting a blank line! It means that you
        # submitted EOF as the first character of a line, so there was nothing
        # in parts[0]. If EOF is in the middle of the line we'll still yield the
        # first bit before breaking the loop.
        if line == '':
            break

        line = line.rstrip('\n')
        yield line

        if has_eof:
            break

def multi_line_input(prompt=None):
    '''
    Yield multiple lines of input from the user, until they submit EOF.
    EOF is usually Ctrl+D on linux and Ctrl+Z on windows.

    The prompt is only shown for non-pipe situations, so you do not need to
    adjust your `prompt` argument for pipe/non-pipe usage.
    '''
    lines = _multi_line_input(prompt=prompt)
    if not IN_PIPE:
        # Wait until the user finishes all their lines before continuing.
        # The caller might be processing + printing these lines in a loop
        # and it would be weird if they start outputting before the user has
        # finished inputting.
        lines = list(lines)
    return lines

def input(
        arg,
        *,
        input_prompt=None,
        read_files=False,
        skip_blank=False,
        strip=False,
    ):
    arg_lower = arg.lower()

    if arg_lower in INPUT_STRINGS:
        lines = multi_line_input(prompt=input_prompt)

    elif arg_lower in CLIPBOARD_STRINGS:
        import pyperclip
        lines = pyperclip.paste().splitlines()

    elif read_files and os.path.isfile(arg):
        lines = open(arg, 'r', encoding='utf-8')

    else:
        lines = arg.splitlines()

    for line in lines:
        if strip:
            line = line.strip()
        if skip_blank and not line:
            continue
        yield line

def output(line, end='\n'):
    sys.stdout.write(line)
    if not line.endswith(end):
        sys.stdout.write(end)
    if not OUT_PIPE:
        sys.stdout.flush()

def go(args=None, *input_args, **input_kwargs):
    '''
    Automatically resolve all commandline arguments, or read from stdin if
    there are no arguments.

    This function is only useful if you have *no other arguments* besides your
    program's main data sink. You will not be able to use argparse in
    conjunction with this function. If you want to support more arguments,
    it's better to use a regular argparse argument which is then passed into
    pipeable.input to resolve it for your data sink.
    '''
    if args is None:
        args = sys.argv[1:]

    if not args:
        # There are no arguments, and...
        if IN_PIPE:
            # we are being piped to, so read the pipe.
            args = [INPUT_STRINGS[0]]
        else:
            # we are on the terminal, so cry for help.
            raise NoArguments()

    for arg in args:
        yield from input(arg, *input_args, **input_kwargs)
