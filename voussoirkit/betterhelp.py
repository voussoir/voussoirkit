import argparse
try:
    import colorama
except ImportError:
    colorama = None
import io
import os
import re
import shlex
import sys
import textwrap

from voussoirkit import dotdict
from voussoirkit import niceprints
from voussoirkit import pipeable
from voussoirkit import subproctools
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

# When using a single parser or a command of a subparser, the presence of any
# of these strings in argv will trigger the helptext.
# > application.py --help
# > application.py command --help
HELP_ARGS = {'-h', '--help'}

# When using a subparser, the command name can be any of these to trigger
# the helptext.
# > application.py help
# > application.py --help
# This does not apply to single-parser applications because the user might try
# to pass the word "help" as the actual argument to the program, but in a
# subparser application it's very unlikely that there is an actual command
# called help.
HELP_COMMANDS = {'help', '-h', '--help'}

# Modules can add additional helptexts to this set, and they will appear
# after the program's main docstring is shown. This is used when the module
# intercepts sys.argv to change program behavior beyond the options provided
# by the program's argparse. For example, voussoirkit.vlogging.main_decorator
# adds command-line arguments like --debug which the application's argparse
# is not aware of. vlogging registers an epilogue here so that all vlogging-
# enabled applications gain the relevant helptext for free.
HELPTEXT_EPILOGUES = set()

# INTERNALS
################################################################################

def can_use_bare(parser) -> bool:
    '''
    Return true if the given parser has no required arguments, ie can run bare.
    This is used to decide whether running `> myprogram.py` should show the
    helptext or just run normally.
    '''
    has_func = bool(parser.get_default('func'))
    has_required_args = any(is_required(action) for action in parser._actions)
    return has_func and not has_required_args

def can_use_bare_subparsers(subparser_action) -> set:
    '''
    Return a set of subparser names which can be used bare.
    '''
    can_bares = set(
        sp_name for (sp_name, sp) in subparser_action.choices.items()
        if can_use_bare(sp)
    )
    return can_bares

def get_program_name():
    program_name = os.path.basename(sys.argv[0])
    program_name = re.sub(r'\.pyw?$', '', program_name)
    return program_name

def get_subparser_action(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None

def get_subparsers(parser):
    '''
    Return a dictionary mapping subparser actions to a list of their aliases,
    i.e. {parser: [names]}
    '''
    action = get_subparser_action(parser)
    if action is None:
        return {}

    subparsers = {}
    for (sp_name, sp) in action.choices.items():
        subparsers.setdefault(sp, []).append(sp_name)
    return subparsers

def is_required(action):
    # I found that positional arguments marked with nargs=* were still being
    # considered 'required', which is not what I want as far as can_use_bare
    # goes. I believe option_strings==[] is what indicates this action is
    # positional. If I'm wrong let's fix it.
    if action.option_strings == [] and action.nargs == '*':
        return False
    return action.required

def listget(li, index, fallback=None):
    try:
        return li[index]
    except IndexError:
        return fallback

def listsplit(li, target, count=float('inf')):
    '''
    Split a list into multiple lists wherever the target element appears.
    '''
    newli = []
    subli = []
    for item in li:
        if item == target and count > 0:
            newli.append(subli)
            subli = []
            count -= 1
        else:
            subli.append(item)
    newli.append(subli)
    return newli

def make_helptext(
        parser,
        all_command_names=None,
        command_name=None,
        do_colors=True,
        do_headline=True,
        full_subparsers=False,
        program_name=None,
    ):
    # Even though this text is going out on stderr, we only colorize it if
    # both stdout and stderr are tty because as soon as pipe buffers are
    # involved, even on stdout, things start to get weird.
    if do_colors and colorama and pipeable.stdout_tty() and pipeable.stderr_tty():
        colorama.init()
        color = dotdict.DotDict(
            positional=colorama.Style.BRIGHT + colorama.Fore.CYAN,
            named=colorama.Style.BRIGHT + colorama.Fore.GREEN,
            flag=colorama.Style.BRIGHT + colorama.Fore.MAGENTA,
            command=colorama.Style.BRIGHT + colorama.Fore.YELLOW,
            reset=colorama.Style.RESET_ALL,
            required_asterisk=colorama.Style.BRIGHT + colorama.Fore.RED + '(*)' + colorama.Style.RESET_ALL,
        )
    else:
        color = dotdict.DotDict(
            positional='',
            named='',
            flag='',
            command='',
            reset='',
            required_asterisk='(*)',
        )

    if program_name is None:
        program_name = get_program_name()

    if command_name is None:
        invoke_name = program_name
    else:
        invoke_name = f'{program_name} {color.command}{command_name}{color.reset}'

    # If we are currently generating the helptext for a subparser, the caller
    # can give us the names of all other command names, so that we can colorize
    # them if this subparser references another one in its text. Otherwise, we
    # will only gather up subparsers below the given parser object.
    if all_command_names is None:
        all_command_names = set()

    # GATHER UP ARGUMENT TYPES
    # Here we go through the list of actions in the parser and classify them
    # into a few basic types, which will be rendered and colorized in
    # different ways.

    all_positional_names = set()
    all_named_names = set()
    all_flags_names = set(HELP_ARGS)
    dest_to_action = {}
    main_invocation = [invoke_name]
    positional_actions = []
    named_actions = []
    required_named_actions = []
    optional_named_actions = []
    flag_types = {argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._StoreConstAction}
    flag_actions = []

    for action in parser._actions:
        if type(action) is argparse._HelpAction:
            continue

        if type(action) is argparse._SubParsersAction:
            all_command_names.update(action.choices.keys())
            continue

        if type(action) is argparse._StoreAction:
            if action.option_strings == []:
                positional_actions.append(action)
                all_positional_names.add(action.dest)
            else:
                named_actions.append(action)
                if action.required:
                    required_named_actions.append(action)
                else:
                    optional_named_actions.append(action)
                all_named_names.update(action.option_strings)
        elif type(action) in flag_types:
            flag_actions.append(action)
            all_flags_names.update(action.option_strings)
        else:
            raise TypeError(f'betterhelp doesn\'t know what to do with {action}.')
        dest_to_action[action.dest] = action

    # COLORIZE ARGUMENT INVOCATIONS
    # Here we generate invocation strings for each of the arguments. That is,
    # an argument called `--scales` with type=int and nargs=+ will be shown as
    # `--scales int [int, ...]`. Each type of argument has different
    # considerations involving the dest, type, metavar, nargs, etc.
    # The required arguments will be added to the main_invocation, the optional
    # arguments will simply wait in the action_invocations dictionary until we
    # show their full help in an upcoming section.

    def render_nargs(argname, nargs):
        if nargs is None:
            return argname
        elif isinstance(nargs, int):
            return ' '.join([argname] * nargs)
        elif nargs == '?':
            return f'[{argname}]'
        elif nargs == '*':
            return f'[{argname}, {argname}, ...]'
        elif nargs == '+':
            return f'{argname} [{argname}, ...]'
        elif nargs == '...':
            return f'[{argname}, ...]'

    action_invocations = {}
    for action in positional_actions:
        if action.type is not None:
            typename = f'({action.type.__name__})'
        else:
            typename = ''

        if action.metavar is not None:
            argname = action.metavar
        else:
            argname = action.dest

        inv = render_nargs(argname, action.nargs)
        inv = f'{color.positional}{inv}{typename}{color.reset}'
        action_invocations[action] = [inv]
        main_invocation.append(inv)

    ##

    for action in named_actions:
        action_invocations[action] = []
        for alias in action.option_strings:
            if action.metavar is not None:
                argname = action.metavar
            elif action.type is None:
                argname = action.dest
            else:
                argname = action.type.__name__

            inv = render_nargs(argname, action.nargs)
            inv = f'{color.named}{alias} {inv}{color.reset}'
            action_invocations[action].append(inv)

    for action in required_named_actions:
        main_invocation.append(action_invocations[action][0])

    if optional_named_actions:
        main_invocation.append(f'{color.named}[options]{color.reset}')

    ##

    for action in flag_actions:
        action_invocations[action] = []
        for alias in action.option_strings:
            inv = f'{color.flag}{alias}{color.reset}'
            action_invocations[action].append(inv)

    if flag_actions:
        main_invocation.append(f'{color.flag}[flags]{color.reset}')

    # COLORIZE ARGUMENT NAMES THAT APPEAR IN OTHER TEXTS
    # Now that we know the names of all the different types of arguments, we
    # can use them to colorize the program description and the help text of
    # each individual argument. This makes it really easy to see when one
    # argument has an influence on another argument.
    # If you use a positional argument that is a common noun this can be
    # a bit annoying.

    def colorize_names(text):
        for command in all_command_names:
            text = re.sub(rf'((?:^|\s){command}(?:\b))', rf'{color.command}\1{color.reset}', text)
        for positional in all_positional_names:
            text = re.sub(rf'((?:^|\s){positional}(?:\b))', rf'{color.positional}\1{color.reset}', text)
        for named in all_named_names:
            text = re.sub(rf'((?:^|\s){named}(?:\b))', rf'{color.named}\1{color.reset}', text)
        for flag in all_flags_names:
            text = re.sub(rf'((?:^|\s){flag}(?:\b))', rf'{color.flag}\1{color.reset}', text)
        return text

    # PUTTING TOGETHER PROGRAM DESCRIPTION & ARGUMENT HELPS
    # This is the portion that actually constructs the majority of the help
    # text, by combining the program's own help description with the invocation
    # tips and help texts of each of the arguments.

    program_description = parser.description or ''
    program_description = textwrap.dedent(program_description).strip()
    program_description = colorize_names(program_description)

    argument_helps = []
    for action in (positional_actions + named_actions + flag_actions):
        inv = '\n'.join(action_invocations[action])
        arghelp = []
        if action.help is not None:
            arghelp.append(textwrap.dedent(action.help).strip())
        if type(action) is argparse._StoreAction and action.default is not None:
            arghelp.append(f'Default: {repr(action.default)}')
        if action.option_strings and action.required:
            arghelp.append(f'{color.required_asterisk} Required{color.reset}')
        arghelp = '\n'.join(arghelp)

        arghelp = colorize_names(arghelp)

        arghelp = textwrap.indent(arghelp, '    ')
        argument_helps.append(f'{inv}\n{arghelp}'.strip())

    if len(main_invocation) > 1 or can_use_bare(parser):
        main_invocation = ' '.join(main_invocation)
        main_invocation = f'> {main_invocation}'
    else:
        main_invocation = ''

    # SUBPARSER PREVIEWS
    # If this program has subparsers, we will generate a preview of their name
    # and description. If full_subparsers is True, we also show their full
    # invocation and argument helps.

    subparser_previews = []
    for (sp, aliases) in get_subparsers(parser).items():
        sp_help = []
        for alias in aliases:
            sp_help.append(f'{program_name} {color.command}{alias}{color.reset}')
        if full_subparsers:
            desc = make_helptext(
                sp,
                command_name=aliases[0],
                do_headline=False,
                all_command_names=all_command_names,
            )
            desc = textwrap.dedent(desc).strip()
            desc = textwrap.indent(desc, '    ')
            sp_help.append(f'{desc}')
        elif sp.description is not None:
            first_para = textwrap.dedent(sp.description).split('\n\n')[0].strip()
            first_para = textwrap.indent(first_para, '    ')
            sp_help.append(f'{first_para}')
        sp_help = '\n'.join(sp_help)
        subparser_previews.append(sp_help)

    if subparser_previews:
        subparser_previews = '\n\n'.join(subparser_previews)
        subparser_previews = f'{color.command}Commands{color.reset}\n--------\n\n{subparser_previews}'

    # COLORIZE EXAMPLE INVOCATIONS
    # Here we take example invocation strings provided by the program itself,
    # and run them through the argparser to colorize the positional, named,
    # and flag arguments.
    # argparse does not expose to us exactly which input strings led to which
    # members of the outputted namespace, so we have to deduce it based on dest.

    def dear_argparse_please_dont_call_sys_exit_im_trying_to_work_here(message):
        raise TypeError()

    example_invocations = []
    for example in getattr(parser, 'examples', []):
        args = example
        if isinstance(args, dict):
            args = args['args']
        if isinstance(args, str):
            args = shlex.split(args, posix=os.name != 'nt')
        example_invocation = [invoke_name]
        parser.error = dear_argparse_please_dont_call_sys_exit_im_trying_to_work_here

        # more_positional is a list of positional arguments that we will put
        # after -- in the colorized output. Since the argparse namespace will
        # not tell us which positional arguments came from before or after
        # the --, we will have to figure it out ourselves.
        doubledash_parts = listsplit(args, '--', count=1)
        if len(doubledash_parts) == 2:
            more_positional = doubledash_parts[-1]
        else:
            more_positional = []

        # more_positional_verify is a list of arguments we expect to be in
        # more_positional but have not yet seen. This is needed because of the
        # argparse type parameter which means a value in the namespace might
        # not match the string that was inputted and we won't recognize it.
        more_positional_verify = more_positional[:]

        try:
            parsed_example = parser.parse_args(args)
        except TypeError:
            example_invocation.extend(subproctools.quote(arg) for arg in args)
        else:
            keyvals = parsed_example.__dict__.copy()
            keyvals.pop('func', None)
            positional_args = []
            for (dest, value) in list(keyvals.items()):
                action = dest_to_action[dest]
                if value == action.default:
                    keyvals.pop(dest)
                    continue
                if action not in positional_actions:
                    continue
                if action.nargs == '*' and value == []:
                    keyvals.pop(dest)
                    continue
                if isinstance(value, list):
                    positional_args.extend(value)
                else:
                    positional_args.append(value)
                keyvals.pop(dest)

            positional_args2 = []
            for arg in reversed(positional_args):
                try:
                    more_positional_verify.remove(arg)
                except ValueError:
                    positional_args2.append(arg)

            positional_args2.reverse()
            positional_args = positional_args2

            if positional_args:
                positional_inv = ' '.join(subproctools.quote(str(arg)) for arg in positional_args)
                positional_inv = f'{color.positional}{positional_inv}{color.reset}'
                example_invocation.append(positional_inv)
            for (dest, value) in list(keyvals.items()):
                action = dest_to_action[dest]
                if action in named_actions:
                    if isinstance(value, list):
                        value = ' '.join(subproctools.quote(str(arg)) for arg in value)
                    else:
                        value = subproctools.quote(str(value))
                    inv = f'{color.named}{action.option_strings[0]} {value}{color.reset}'
                elif action in flag_actions:
                    inv = f'{color.flag}{action.option_strings[0]}{color.reset}'
                example_invocation.append(inv)

            # While we were looking for more_positional arguments, some of them
            # may have slipped past us because of their type parameter. That is,
            # the parsed namespace contains ints or other objects that were not
            # matched to the strings in more_positional_verify. So, we remove
            # the remaining more_positional_verify from more_positional, and
            # those objects will appear in the regular positional area instead
            # of after the --. This could be problematic if the input string
            # has a leading hyphen and the type parameter turned it into
            # something else (a negative number), but I think it's the best
            # we can do without being able to inspect argparse's decisions.

            # Not using set operations or [x if x not in verify] here because
            # the positional arguments can be duplicates and the quantity of
            # removals matters.
            while more_positional_verify:
                more_positional.remove(more_positional_verify.pop(0))

            if more_positional:
                example_invocation.append('--')
                more_positional = ' '.join(subproctools.quote(str(arg)) for arg in more_positional)
                more_positional = f'{color.positional}{more_positional}{color.reset}'
                example_invocation.append(more_positional)

        example_invocation = ' '.join(example_invocation)
        example_invocation = f'> {example_invocation}'
        if isinstance(example, dict) and example.get('comment'):
            comment = example['comment']
            example_invocation = f'# {comment}\n{example_invocation}'

        if isinstance(example, dict) and example.get('run'):
            _stdout = sys.stdout
            _stderr = sys.stderr
            buffer = io.StringIO()
            sys.stdout = buffer
            sys.stderr = buffer
            try:
                parsed_example.func(parsed_example)
                buffer.seek(0)
                output = buffer.read().strip()
                buffer.close()
                example_invocation = f'{example_invocation}\n{output}'
                sys.stdout = _stdout
                sys.stderr = _stderr
            except Exception:
                sys.stdout = _stdout
                sys.stderr = _stderr
                raise

        example_invocations.append(example_invocation)

    example_invocations = '\n\n'.join(example_invocations)
    if example_invocations:
        example_invocations = f'Examples:\n{example_invocations}'

    if subparser_previews and not full_subparsers:
        subparser_epilogue = textwrap.dedent(f'''
        To see details on each command, run
        > {program_name} {color.command}<command>{color.reset} {color.flag}--help{color.reset}
        ''').strip()
    else:
        subparser_epilogue = None

    # PUT IT ALL TOGETHER

    parts = [
        niceprints.equals_header(program_name) if do_headline else None,
        program_description,
        main_invocation,
        '\n\n'.join(argument_helps),
        subparser_previews,
        subparser_epilogue,
        example_invocations,
    ]
    parts = [part for part in parts if part]
    parts = [part.strip() for part in parts]
    parts = [part for part in parts if part]
    helptext = '\n\n'.join(parts)
    return helptext

def print_helptext(text) -> None:
    '''
    Print the given text to stderr, along with any epilogues added by
    other modules.
    '''
    fulltext = []
    fulltext.append(text.strip())
    epilogues = {textwrap.dedent(epi).strip() for epi in HELPTEXT_EPILOGUES}
    fulltext.extend(sorted(epi.strip() for epi in epilogues))
    separator = '\n' + ('-' * 80) + '\n'
    fulltext = separator.join(fulltext)
    # Ensure one blank line above helptext.
    pipeable.stderr()
    pipeable.stderr(fulltext)

# MAINS
################################################################################

def _go_single(parser, argv, *, args_postprocessor=None):
    can_bare = can_use_bare(parser)

    needs_help = (
        any(arg.lower() in HELP_ARGS for arg in argv) or
        len(argv) == 0 and not can_bare
    )
    if needs_help:
        do_colors = os.environ.get('NO_COLOR', None) is None
        print_helptext(make_helptext(parser, do_colors=do_colors))
        return 1

    args = parser.parse_args(argv)
    if args_postprocessor is not None:
        args = args_postprocessor(args)
    return args.func(args)

def _go_multi(parser, argv, *, args_postprocessor=None):
    subparsers = get_subparser_action(parser).choices
    can_bare = can_use_bare(parser)

    def main(argv):
        args = parser.parse_args(argv)
        if args_postprocessor is not None:
            args = args_postprocessor(args)
        return args.func(args)

    all_command_names = set(subparsers.keys())
    command = listget(argv, 0, '').lower()

    if command == '' and can_bare:
        return main(argv)

    do_colors = os.environ.get('NO_COLOR', None) is None

    if command == 'helpall':
        print_helptext(make_helptext(parser, full_subparsers=True, all_command_names=all_command_names, do_colors=do_colors))
        return 1

    if command == '':
        print_helptext(make_helptext(parser, all_command_names=all_command_names, do_colors=do_colors))
        because = 'you did not choose a command'
        pipeable.stderr(f'\nYou are seeing the default help text because {because}.')
        return 1

    if command in HELP_COMMANDS:
        print_helptext(make_helptext(parser, all_command_names=all_command_names, do_colors=do_colors))
        return 1

    if command not in subparsers:
        print_helptext(make_helptext(parser, all_command_names=all_command_names, do_colors=do_colors))
        because = f'"{command}" was not recognized'
        pipeable.stderr(f'\nYou are seeing the default help text because {because}.')
        return 1

    subparser = subparsers[command]
    arguments = argv[1:]

    no_args = len(arguments) == 0 and not can_use_bare(subparser)
    if no_args or any(arg.lower() in HELP_ARGS for arg in arguments):
        print_helptext(make_helptext(subparser, command_name=command, all_command_names=all_command_names, do_colors=do_colors))
        return 1

    return main(argv)

def go(parser, argv, *, args_postprocessor=None):
    if get_subparser_action(parser):
        return _go_multi(parser, argv, args_postprocessor=args_postprocessor)
    else:
        return _go_single(parser, argv, args_postprocessor=args_postprocessor)
