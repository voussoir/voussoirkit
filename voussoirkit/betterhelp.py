import functools
import textwrap

HELPSTRINGS = {'', 'help', '-h', '--help'}

def docstring_preview(text):
    '''
    This function assumes that your docstring is formatted with a single blank
    line separating the command's primary summary and the rest of the text.
    For example:

        cookbacon = """
        cookbacon: Cooks all nearby bacon to a specified temperature.

        Usage:
            > cookbacon 350F
            > cookbacon 175C
        """

    and will return the first portion.
    '''
    text = text.split('\n\n')[0].strip()
    return text

def listget(li, index, fallback=None):
    try:
        return li[index]
    except IndexError:
        return fallback

def add_previews(docstring, sub_docstrings):
    '''
    Given a primary docstring which contains {command_name} formatting elements,
    and a dict of sub_docstrings of {command_name: docstring}, insert previews
    of each command into the primary docstring.
    '''
    previews = {
        sub_name: docstring_preview(sub_text)
        for (sub_name, sub_text) in sub_docstrings.items()
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
