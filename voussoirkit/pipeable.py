# import pyperclip moved to stay lazy.
import sys

builtin_input = input

CLIPBOARD_STRINGS = ['!c', '!clip', '!clipboard']
INPUT_STRINGS = ['!i', '!in', '!input', '!stdin']
EOF = '\x1a'

IN_PIPE = not sys.stdin.isatty()
OUT_PIPE = not sys.stdout.isatty()

class PipeableException(Exception):
    pass

class NoArguments(PipeableException):
    pass
def argv(index):
    try:
        return sys.argv[index]
    except IndexError:
        return None

def multi_line_input(prompt=None):
    if prompt is not None and not IN_PIPE:
        sys.stderr.write(prompt)
        sys.stderr.flush()

    has_eof = False
    while not has_eof:
        line = sys.stdin.readline()
        parts = line.split(EOF)
        line = parts[0]
        has_eof = len(parts) > 1
        if line == '':
            break
        line = line.rstrip('\n')
        yield line

def input(arg=None, *, input_prompt=None, skip_blank=False, strip=False):
    if arg is not None:
        arg_lower = arg.lower()

    if arg is None:
        if IN_PIPE:
            lines = multi_line_input()
        else:
            raise ValueError(arg)

    elif arg_lower in INPUT_STRINGS:
        lines = multi_line_input(prompt=input_prompt)
        if not IN_PIPE:
            # Wait until the user finishes all their lines before continuing.
            lines = list(lines)

    elif arg_lower in CLIPBOARD_STRINGS:
        import pyperclip
        lines = pyperclip.paste().splitlines()

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
