import functools
import textwrap

HELPSTRINGS = {'', 'help', '-h', '--help'}

def docstring_preview(text):
    text = text.split('\n\n')[0].strip()
    return text

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
            argument = listget(argv, 0, '').lower()

            if argument in HELPSTRINGS:
                print(docstring)
                return 1

            return main(argv)
        return wrapped
    return wrapper

def subparser_betterhelp(main_docstring, sub_docstrings):
    def wrapper(main):
        def wrapped(argv):
            command = listget(argv, 0, '').lower()

            if command not in sub_docstrings:
                print(main_docstring)
                if command == '':
                    print('You are seeing the default help text because you did not choose a command.')
                elif command not in HELPSTRINGS:
                    print(f'You are seeing the default help text because "{command}" was not recognized')
                return 1

            argument = listget(argv, 1, '').lower()
            if argument in HELPSTRINGS:
                print(sub_docstrings[command])
                return 1

            return main(argv)
        return wrapped
    return wrapper
