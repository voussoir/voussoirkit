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
