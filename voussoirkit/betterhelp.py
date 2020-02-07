import argparse
import functools

HELPSTRINGS = {'', 'help', '-h', '--help'}

def can_use_bare(parser):
    has_func = bool(parser.get_default('func'))
    has_required_args = any(action.required for action in parser._actions)
    return has_func and not has_required_args

def can_use_bare_subparsers(subparser_action):
    can_bares = set(
        sp_name for (sp_name, sp) in subparser_action.choices.items()
        if can_use_bare(sp)
    )
    return can_bares

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

def betterhelp(parser, docstring):
    '''
    This decorator actually doesn't need the `parser`, but the
    subparser_betterhelp decorator does, so in the interest of having similar
    function signatures I'm making it required here too. I figure it's the
    lesser of two evils. Plus, maybe someday I'll find a need for it and won't
    have to make any changes to do it.
    '''
    can_bare = can_use_bare(parser)
    def wrapper(main):
        @functools.wraps(main)
        def wrapped(argv):
            argument = listget(argv, 0, '').lower()

            if argument == '' and can_bare:
                pass
            elif argument in HELPSTRINGS:
                print(docstring)
                return 1

            return main(argv)
        return wrapped
    return wrapper

def get_subparser_action(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise TypeError('Couldn\'t locate the SubParsersAction.')

def set_alias_docstrings(sub_docstrings, subparser_action):
    '''
    When using subparser aliases:

        subp = parser.add_subparser('command', aliases=['comm'])

    The _SubParsersAction will contain a dictionary `choices` of
    {'command': ArgumentParser, 'comm': ArgumentParser}.
    This choices dict does not indicate which one was the original name;
    all aliases are equal. So, we'll identify which names are aliases because
    their ArgumentParsers will have the same ID in memory. And, as long as one
    of those aliases is in the provided docstrings, all the other aliases will
    get that docstring too.
    '''
    sub_docstrings = {name.lower(): docstring for (name, docstring) in sub_docstrings.items()}
    aliases = {}
    primary_aliases = {}
    for (sp_name, sp) in subparser_action.choices.items():
        sp_name = sp_name.lower()
        aliases.setdefault(id(sp), []).append(sp_name)
        if sp_name in sub_docstrings:
            primary_aliases[id(sp)] = sp_name

    for (sp_id, sp_aliases) in aliases.items():
        primary_alias = primary_aliases[sp_id]
        for sp_alias in sp_aliases:
            sub_docstrings[sp_alias] = sub_docstrings[primary_alias]

    return sub_docstrings

def subparser_betterhelp(parser, main_docstring, sub_docstrings):
    subparser_action = get_subparser_action(parser)
    sub_docstrings = set_alias_docstrings(sub_docstrings, subparser_action)
    can_bare = can_use_bare(parser)
    can_bares = can_use_bare_subparsers(subparser_action)

    def wrapper(main):
        @functools.wraps(main)
        def wrapped(argv):
            command = listget(argv, 0, '').lower()

            if command == '' and can_bare:
                return main(argv)

            if command not in sub_docstrings:
                print(main_docstring)
                if command == '':
                    because = 'you did not choose a command.'
                    print(f'You are seeing the default help text because {because}')
                elif command not in HELPSTRINGS:
                    because = f'"{command}" was not recognized'
                    print(f'You are seeing the default help text because {because}')
                return 1

            argument = listget(argv, 1, '').lower()
            if argument == '' and command in can_bares:
                pass
            elif argument in HELPSTRINGS:
                print(sub_docstrings[command])
                return 1

            return main(argv)
        return wrapped
    return wrapper
