'''
This module provides functions for interactive command line UIs.
'''
####################################################################################################
## ABC_CHOOSER #####################################################################################
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

def abc_chooser(options, prompt='', must_pick=False):
    '''
    Given a list of options, the user will pick one by the corresponding letter.
    The return value is the item from the options list, or None if must_pick is
    False and the user entered nothing.
    '''
    option_letters = _abc_make_option_letters(options)

    while True:
        message = []
        for (letter, option) in option_letters.items():
            message.append(f'{letter}. {option}')
        print('\n'.join(message))
        choice = input(prompt).strip().lower()

        if not choice:
            if must_pick:
                print()
                continue
            else:
                return

        if choice not in option_letters:
            print()
            continue

        return option_letters[choice]

def abc_chooser_many(options, prompt='', label='X'):
    '''
    Given a list of options, the user may pick zero or many options by their
    corresponding letter. They can toggle the options on and off as long as
    they like, and submit their selection by entering one more blank line.
    The return value is a list of items from the options list.
    '''
    selected = set()
    option_letters = _abc_make_option_letters(options)

    while True:
        message = []
        for (letter, option) in option_letters.items():
            this_label = label if letter in selected else ''
            this_label = this_label.center(len(label))
            message.append(f'{letter}. [{this_label}] {option}')
        print('\n'.join(message))

        choice = input(prompt).strip().lower()

        if not choice:
            break

        if choice not in option_letters:
            print()
            continue

        if choice in selected:
            selected.remove(choice)
        else:
            selected.add(choice)
        print()

    choices = [option_letters[letter] for letter in option_letters if letter in selected]
    return choices

####################################################################################################
## GETPERMISSION ###################################################################################
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

    You can customize the strings that mean yes or no. For example, you could
    create a "type the name of the thing you're about to delete" prompt.

    If `must_pick`, then undecided is not allowed and the input will repeat
    until they choose an acceptable answer. Either way, the intended usage of
    `if getpermission():` will always only accept in case of explicit yes.
    '''
    if prompt is not None:
        print(prompt)
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
