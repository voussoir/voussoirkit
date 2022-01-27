'''
This module provides functions for making your program easy to pipe to and from
via the command line.

Pipeable expects a little bit of buy-in with respect to the !i and !c strings.
In traditional unix tools, reading from stdin is sometimes enabled
automatically when the program detects its input is a pipe instead of a
keyboard, sometimes enabled by passing "-" to the argument that would otherwise
read a file, and sometimes implied by a lack of arguments. Following Python's
philosophy of explicit is better than implicit, I prefer using a consistent
argparser and letting !i indicate stdin. This also means you can write programs
where any of the arguments might be !i, unlike most traditional unix tools where
only the primary data sink reads stdin.
'''
# import pyperclip moved to stay lazy.
import os
import sys

CLIPBOARD_STRINGS = ['!c', '!clip', '!clipboard']
INPUT_STRINGS = ['!i', '!in', '!input', '!stdin']
EOF = '\x1a'

class PipeableException(Exception):
    pass

class NoArguments(PipeableException):
    pass

def ctrlc_return1(function):
    '''
    Apply this decorator to your argparse gateways or main function, and if the
    user presses ctrl+c then the gateway will return 1 as its status code
    without the stacktrace appearing.

    This helps me avoid wrapping the entire function in a try-except block.

    Don't use this if you need to perform some other kind of cleanup on ctrl+c.
    '''
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyboardInterrupt:
            return 1
    return wrapped

def _multi_line_input(prompt=None):
    if prompt is not None and not stdin_pipe():
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
    if stdin_tty():
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
        split_lines=True,
        strip=False,
    ):
    '''
    Given an argument (probably from the command line), resolve it into an
    iterable of lines if split_lines is True, or return the whole text.

    If the arg is in CLIPBOARD_STRINGS, the contents of the clipboard are taken.
    If the arg is in INPUT_STRINGS, input is read from stdin with an optional
    input_prompt. The prompt is only shown during non-pipe input (typing).
    If read_files is True and the arg is the path to an existing file, the file
    is read as utf-8 text.
    If none of the above, then the argument string is taken literally.

    Resolution is not recursive: if the clipboard contains the name of a file,
    it won't be read, etc.

    In addition to the above resolution techniques, you also have the option to
    strip lines before yielding them, and skip lines which are emptystring (if
    strip is False, then all-whitespace lines will still be yielded). If you're
    modifying input but overall maintaining its original structure, you probably
    want these both False. If you're just crunching numbers you probably want
    them both True. If split_lines is False then these are not relevant.

    So, your calling code should not have to make any adjustments -- just call
    this function however is appropriate for your data sink and enjoy.
    '''
    if not isinstance(arg, str):
        raise TypeError(f'arg should be {str}, not {type(arg)}.')

    arg_lower = arg.lower()

    if arg_lower in INPUT_STRINGS:
        lines = multi_line_input(prompt=input_prompt)
        if not split_lines:
            text = '\n'.join(lines)

    elif arg_lower in CLIPBOARD_STRINGS:
        import pyperclip
        text = pyperclip.paste()
        if split_lines:
            lines = text.splitlines()

    elif read_files and os.path.isfile(arg):
        with open(arg, 'r', encoding='utf-8') as handle:
            text = handle.read()
        if split_lines:
            lines = text.splitlines()

    else:
        text = arg
        if split_lines:
            lines = text.splitlines()

    if not split_lines:
        return text

    if strip:
        lines = (line.strip() for line in lines)
    if skip_blank:
        lines = (line for line in lines if line)

    return lines

def input_many(args, *input_args, **input_kwargs):
    '''
    Given a list of input arguments, yield the input() results for all of them.
    This saves you from having to write the double for loop yourself.
    This is useful when writing an argparser with nargs='+' where each arg
    might be a string or !i or !c.
    '''
    if isinstance(args, str):
        yield from input(args, *input_args, **input_kwargs)
        return

    for arg in args:
        yield from input(arg, *input_args, **input_kwargs)

def output(stream, line, *, end):
    line = str(line)
    stream.write(line)
    if not line.endswith(end):
        stream.write(end)
    if stream.isatty():
        stream.flush()

def stdout(line='', end='\n'):
    # In pythonw, stdout is None.
    if sys.stdout is not None:
        output(sys.stdout, line, end=end)

def stderr(line='', end='\n'):
    # In pythonw, stderr is None.
    if sys.stderr is not None:
        output(sys.stderr, line, end=end)

# In pythonw, stdin and stdout are None.
def stdin_tty():
    if sys.stdin is not None and sys.stdin.isatty():
        return sys.stdin

def stdout_tty():
    if sys.stdout is not None and sys.stdout.isatty():
        return sys.stdout

def stderr_tty():
    if sys.stderr is not None and sys.stderr.isatty():
        return sys.stderr

def stdin_pipe():
    if sys.stdin is not None and not sys.stdin.isatty():
        return sys.stdin

def stdout_pipe():
    if sys.stdout is not None and not sys.stdout.isatty():
        return sys.stdout

def stderr_pipe():
    if sys.stderr is not None and not sys.stderr.isatty():
        return sys.stderr

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
        if stdin_pipe():
            # we are being piped to, so read the pipe.
            args = [INPUT_STRINGS[0]]
        else:
            # we are on the terminal, so cry for help.
            raise NoArguments()

    for arg in args:
        yield from input(arg, *input_args, **input_kwargs)
