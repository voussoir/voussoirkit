'''
This module provides functions for generating random strings.
'''
import math
import os
import random
import string
import sys

DEFAULT_LENGTH = 32
DEFAULT_SENTENCE = 5
HELP_MESSAGE = '''
===============================================================================
Generates a randomized password.

> passwordy [length] [options]

    length: How many characters. Default %03d.
    options:
        h  : consist entirely of hexadecimal characters.
        b  : consist entirely of binary characters.
        dd : consist entirely of decimal characters.
        default : consist entirely of upper+lower letters.

        p  : allow punctuation in conjunction with above.
        d  : allow digits in conjunction with above.

        l  : convert to lowercase.
        u  : convert to uppercase.
        nd : no duplicates. Each character can only appear once.

Examples:
> passwordy 32 h l
98f17b6016cf08cc00f2aeecc8d8afeb

> passwordy 32 h u
2AA706866BF7A5C18328BF866136A261

> passwordy 32 u
JHEPTKCEFZRFXILMASHNPSTFFNWQHTTN

> passwordy 32 p
Q+:iSKX!Nt)ewUvlE*!+^D}hp+|<wpJ}

> passwordy 32 l p
m*'otz/"!qo?-^wwdu@fasf:|ldkosi`

===============================================================================

Generates a randomized sentence of words.

> passwordy sent [length] [join]

    length : How many words. Default %03d.
    join   : The character that will join words together.
             Default space.

Examples:
> passwordy sent
arrowroot sheared rustproof undo propionic acid

> passwordy sent 8
cipher competition solid angle rigmarole lachrymal social class critter consequently

> passwordy sent 8 _
Kahn_secondary_emission_unskilled_superior_court_straight_ticket_voltameter_hopper_crass

===============================================================================
 '''.strip() % (DEFAULT_LENGTH, DEFAULT_SENTENCE)


def listget(li, index, fallback=None):
    try:
        return li[index]
    except IndexError:
        return fallback

def make_password(length=None, passtype='standard'):
    '''
    Returns a string of length `length` consisting of a random selection
    of uppercase and lowercase letters, as well as punctuation and digits
    if parameters permit
    '''
    if length is None:
        length = DEFAULT_LENGTH

    alphabet = ''

    if 'standard' in passtype:
        alphabet = string.ascii_letters
    elif 'digit_only' in passtype:
        alphabet = string.digits
    elif 'hex' in passtype:
        alphabet = '0123456789abcdef'
    elif 'binary' in passtype:
        alphabet = '01'

    if '+digits' in passtype:
        alphabet += string.digits
    if '+punctuation' in passtype:
        alphabet += string.punctuation
    if '+lowercase' in passtype:
        alphabet = alphabet.lower()
    elif '+uppercase' in passtype:
        alphabet = alphabet.upper()

    alphabet = list(set(alphabet))

    if '+noduplicates' in passtype:
        if len(alphabet) < length:
            message = 'Alphabet "%s" is not long enough to support no-dupe password of length %d'
            message = message % (alphabet, length)
            raise Exception(message)
        password = ''
        for x in range(length):
            random.shuffle(alphabet)
            password += alphabet.pop(0)
    else:
        password = ''.join(random.choices(alphabet, k=length))
    return password

def make_sentence(length=None, joiner=' '):
    '''
    Returns a string containing `length` words, which come from
    dictionary.common.
    '''
    import dictionary.common as common
    if length is None:
        length = DEFAULT_LENGTH
    words = random.choices(common.words, k=length)
    words = [w.replace(' ', joiner) for w in words]
    result = joiner.join(words)
    return result

def random_hex(length):
    randbytes = os.urandom(math.ceil(length / 2))
    token = ''.join('{:02x}'.format(x) for x in randbytes)
    token = token[:length]
    return token

def urandom_hex(length):
    randbytes = os.urandom(math.ceil(length / 2))
    token = ''.join('{:02x}'.format(x) for x in randbytes)
    token = token[:length]
    return token

def main_password(argv):
    length = listget(argv, 0, DEFAULT_LENGTH)
    options = [a.lower() for a in argv[1:]]

    if '-' in length:
        length = length.replace(' ', '')
        length = [int(x) for x in length.split('-', 1)]
        length = random.randint(*length)

    elif not length.isdigit() and options == []:
        options = [length]
        length = DEFAULT_LENGTH

    length = int(length)

    passtype = 'standard'
    if 'dd' in options:
        passtype = 'digit_only'
    if 'b' in options:
        passtype = 'binary'
    if 'h' in options:
        passtype = 'hex'

    if 'l' in options:
        passtype += '+lowercase'
    elif 'u' in options:
        passtype += '+uppercase'
    if 'p' in options:
        passtype += '+punctuation'
    if 'd' in options:
        passtype += '+digits'
    if 'nd' in options:
        passtype += '+noduplicates'

    return make_password(length, passtype=passtype)

def main_sentence(argv):
    length = listget(argv, 1, DEFAULT_SENTENCE)
    joiner = listget(argv, 2, ' ')

    try:
        length = int(length)
    except ValueError:
        joiner = length
        length = DEFAULT_SENTENCE

    return make_sentence(length, joiner)

def main_urandom(argv):
    length = listget(argv, 1, DEFAULT_LENGTH)
    length = int(length)
    return urandom_hex(length)

def main(argv):
    mode = listget(argv, 0, 'password')
    if 'help' in mode:
        print(HELP_MESSAGE)
        quit()

    if 'sent' in mode:
        print(main_sentence(argv))
    elif 'urandom' in mode:
        print(main_urandom(argv))
    else:
        print(main_password(argv))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
