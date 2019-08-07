import functools

def docstring_preview(text, indent=None):
    text = text.split('\n\n')[0]
    if indent:
        text = _indent(text, spaces=indent)
    return text

def indent(text, spaces=4):
    spaces = ' ' * spaces
    return '\n'.join(spaces + line if line.strip() != '' else line for line in text.split('\n'))
_indent = indent

def listget(li, index, fallback=None):
    try:
        return li[index]
    except IndexError:
        return fallback

def add_previews(docstring, sub_docstrings):
    previews = {
        key: docstring_preview(value)
        for (key, value) in sub_docstrings.items()
    }
    docstring = docstring.format(**previews)
    return docstring

def betterhelp(docstring):
    def wrapper(main):
        def wrapped(argv):
            helpstrings = {'', 'help', '-h', '--help'}

            argument = listget(argv, 0, '').lower()

            if argument in helpstrings:
                print(docstring)
                return 1

            return main(argv)
        return wrapped
    return wrapper

def subparser_betterhelp(main_docstring, sub_docstrings):
    def wrapper(main):
        def wrapped(argv):
            helpstrings = {'', 'help', '-h', '--help'}

            command = listget(argv, 0, '').lower()

            if command not in sub_docstrings:
                print(main_docstring)
                if command == '':
                    print('You are seeing the default help text because you did not choose a command.')
                elif command not in helpstrings:
                    print(f'You are seeing the default help text because "{command}" was not recognized')
                return 1

            argument = listget(argv, 1, '').lower()
            if argument in helpstrings:
                print(sub_docstrings[command])
                return 1

            return main(argv)
        return wrapped
    return wrapper
