import os

def quote(arg) -> str:
    if os.name == 'nt':
        # If the command contains comma, semicolon, or equals, only the left
        # half is considered the command and the rest is considered the first
        # argument. If these characters are in other arguments they are
        # sometimes parsed as separate by builtin commands like del, but not
        # separate for external applications.
        # Ampersand, pipe, and caret are process flow and special escape.
        # Quotes inside quotes must be doubled up.
        badchars = [',', ';', '=', '&', '|', '^', '"']
        if arg == '' or any(c.isspace() for c in arg) or any(c in arg for c in badchars):
            arg = arg.replace('"', '""')
            arg = f'"{arg}"'
        return arg
    else:
        # Semicolon is command delimiter.
        # Equals assigns shell variables.
        # Quotes inside quotes must be escaped with backslash.
        badchars = [' ', ';', '=', '&', '|']
        if arg == '' or any(c.isspace() for c in arg) or any(c in arg for c in badchars):
            arg = arg.replace("'", "\\'")
            arg = f"'{arg}'"
        return arg

def format_command(command) -> str:
    cmd = [quote(x) for x in command]
    cmd = ' '.join(cmd)
    cmd = cmd.strip()
    return cmd

def print_command(command, prefix=''):
    print(prefix + format_command(command))
