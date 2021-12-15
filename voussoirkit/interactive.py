'''
This module provides functions for interactive command line UIs.
'''
import sys

from voussoirkit import pipeable

def assert_stdin():
    if sys.stdin is None:
        raise RuntimeError('Interactive functions don\'t work when stdin is None.')

####################################################################################################
# ABC_CHOOSER ######################################################################################
####################################################################################################

def _abc_make_option_letters(options):
    import math
    import string
    from voussoirkit import basenumber
    option_letters = {}
    letter_length = math.ceil(len(options) / 26)
    for (index, option) in enumerate(options):
        letter = basenumber.to_base(index, 26, alphabet=string.ascii_lowercase)
        letter = letter.rjust(letter_length, 'a')
        option_letters[letter] = option

    return option_letters

def abc_chooser(options, *, prompt='', must_pick=False, tostring=None):
    '''
    Given a list of options, the user will pick one by the corresponding letter.
    The return value is the item from the options list, or None if must_pick is
    False and the user entered nothing.

    options:
        A list of options to choose from. The returned value will be one of
        these, or None if must_pick is false and the user made no selection.

    prompt:
        A prompt string to appear at the bottom of the menu where the user
        makes their choice.

    must_pick:
        If True, the menu will keep repeating until the user makes a choice.
        If False, the user can submit a blank line to choose None.

    tostring:
        A function that converts the items from options into strings. Use this
        if the objects' normal __str__ method is not suitable for your menu.
        This way you don't have to convert your objects into strings and then
        back again after getting the returned choice.
    '''
    assert_stdin()

    option_letters = _abc_make_option_letters(options)
    if tostring is not None:
        options_rendered = {letter: tostring(option) for (letter, option) in option_letters.items()}
    else:
        options_rendered = option_letters

    while True:
        for (letter, option) in options_rendered.items():
            pipeable.stderr(f'{letter}. {option}')

        choice = input(prompt).strip().lower()

        if not choice:
            if must_pick:
                pipeable.stderr()
                continue
            else:
                return None

        if choice not in option_letters:
            pipeable.stderr()
            continue

        return option_letters[choice]

def abc_chooser_many(options, *, prompt='', label='X', tostring=None) -> list:
    '''
    Given a list of options, the user may pick zero or more options by their
    corresponding letter. They can toggle the options on and off as many times
    as they like, and submit their selection by entering a blank line.
    The return value is a list of items from the options list.

    options:
        A list of options to choose from. The returned list will be a subset
        of this.

    prompt:
        A prompt string to appear at the bottom of the menu where the user
        makes their choices.

    label:
        This label is placed between square brackets and indicates which
        choices are currently selected. For example [X] or [ACTIVE].

    tostring:
        A function that converts the items from options into strings. Use this
        if the objects' normal __str__ method is not suitable for your menu.
        This way you don't have to convert your objects into strings and then
        back again after getting the returned choices.
    '''
    assert_stdin()

    option_letters = _abc_make_option_letters(options)
    if tostring is not None:
        options_rendered = {letter: tostring(option) for (letter, option) in option_letters.items()}
    else:
        options_rendered = option_letters

    selected = set()
    while True:
        for (letter, option) in options_rendered.items():
            this_label = label if letter in selected else ''
            this_label = this_label.center(len(label))
            pipeable.stderr(f'{letter}. [{this_label}] {option}')

        choice = input(prompt).strip().lower()

        if not choice:
            break

        if choice not in option_letters:
            pipeable.stderr()
            continue

        if choice in selected:
            selected.remove(choice)
        else:
            selected.add(choice)
        pipeable.stderr()

    choices = [option_letters[letter] for letter in sorted(selected)]
    return choices

####################################################################################################
# GETPERMISSION ####################################################################################
####################################################################################################

YES_STRINGS = ['yes', 'y']
NO_STRINGS = ['no', 'n']

def getpermission(
        prompt=None,
        *,
        yes_strings=YES_STRINGS,
        no_strings=NO_STRINGS,
        must_pick=False,
    ):
    '''
    Prompt the user with a yes or no question.

    Return True for yes, False for no, and None if undecided.

    prompt:
        This string will appear above the yes/no input.

    yes_strings,
    no_strings:
        You can customize the strings that mean yes or no. For example, you
        could require the user to confirm a deletion by making the resource name
        the only yes string.
        yes_strings and no_strings should be tuples/lists instead of sets because
        the [0] item will be the one shown on the prompt. The rest are still
        acceptable answers.

    must_pick:
        If True, the menu will keep repeating until the user makes a choice.
        If False, the user can submit a blank line to choose None.
    '''
    assert_stdin()

    if prompt is not None:
        pipeable.stderr(prompt)
    while True:
        answer = input(f'{yes_strings[0]}/{no_strings[0]}> ').strip()
        yes = answer.lower() in (option.lower() for option in yes_strings)
        no = answer.lower() in (option.lower() for option in no_strings)
        if yes or no or not must_pick:
            break

    if yes:
        return True
    if no:
        return False
    return None
