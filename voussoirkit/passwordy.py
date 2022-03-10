'''
This module provides functions for generating random strings. All functions use
cryptographically strong randomness if the operating system supports it, and
non-cs randomness if it does not.

If os.urandom(1) gives you a byte, your system has cs randomness.
'''
import argparse
import math
import os
import random
import string
import sys

from voussoirkit import betterhelp
from voussoirkit import gentools
from voussoirkit import pipeable

try:
    os.urandom(1)
    RNG = random.SystemRandom()
except NotImplementedError:
    RNG = random

def make_password(
        length,
        *,
        binary=False,
        digits=False,
        hex=False,
        letters=False,
        punctuation=False,
    ):
    alphabet = set()
    if letters:
        alphabet.update(string.ascii_letters)
    if digits:
        alphabet.update(string.digits)
    if hex:
        alphabet.update('0123456789abcdef')
    if binary:
        alphabet.update('01')
    if punctuation:
        alphabet.update(string.punctuation)

    if not alphabet:
        raise ValueError('No alphabet options chosen.')

    return ''.join(RNG.choices(tuple(alphabet), k=length))

def make_sentence(length, separator=' '):
    '''
    Returns a string containing `length` words, which come from
    dictionary.common.
    '''
    import dictionary.common as common
    words = RNG.choices(common.words, k=length)
    words = [w.replace(' ', separator) for w in words]
    result = separator.join(words)
    return result

def random_digits(length):
    '''
    Shortcut function for when you don't want to type the make_password call.
    '''
    return ''.join(RNG.choices(string.digits, k=length))

def random_hex(length):
    '''
    Shortcut function for when you don't want to type the make_password call.
    '''
    randbytes = os.urandom(math.ceil(length / 2))
    token = ''.join('{:02x}'.format(x) for x in randbytes)
    token = token[:length]
    return token

def passwordy_argparse(args):
    if args.sentence:
        password = make_sentence(args.length, args.separator)
    else:
        if not any([args.letters, args.digits, args.hex, args.binary, args.punctuation]):
            letters = True
            digits = True
        else:
            letters = args.letters
            digits = args.digits
        password = make_password(
            args.length,
            binary=args.binary,
            digits=digits,
            hex=args.hex,
            letters=letters,
            punctuation=args.punctuation,
        )
    if args.lower:
        password = password.lower()
    elif args.upper:
        password = password.upper()

    if args.groups_of is not None:
        chunks = gentools.chunk_generator(password, args.groups_of)
        chunks = (''.join(chunk) for chunk in chunks)
        password = args.separator.join(chunks)

    prefix = args.prefix or ''
    suffix = args.suffix or ''
    password = f'{prefix}{password}{suffix}'

    pipeable.stdout(password)
    return 0

def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        Generate random passwords using cryptographically strong randomness.
        ''',
    )
    parser.examples = [
        {'args': '32 --letters --digits --punctuation', 'run': True},
        {'args': '48 --hex --upper', 'run': True},
        {'args': '8 --sentence --separator +', 'run': True},
        {'args': '16 --digits --groups-of 4 --separator -', 'run': True},
        {'args': '48 --prefix example.com_ --lower', 'run': True},
    ]
    parser.add_argument(
        'length',
        type=int,
        help='''
        Integer number of characters in normal mode.
        Integer number of words in sentence mode.
        ''',
    )
    parser.add_argument(
        '--sentence',
        action='store_true',
        help='''
        If this argument is passed, the password is made of length random words and
        the other alphabet options are ignored.
        ''',
    )
    parser.add_argument(
        '--groups_of', '--groups-of',
        type=int,
        help='''
        Split the password up into chunks of this many characters, and join them
        back together with the --separator.
        ''',
    )
    parser.add_argument(
        '--separator',
        type=str,
        default=' ',
        help='''
        In sentence mode, the words will be joined with this string.
        In normal mode, the --groups-of chunks will be joined with this string.
        ''',
    )
    parser.add_argument(
        '--letters',
        action='store_true',
        help='''
        Include ASCII letters in the password.
        If none of the other following options are chosen, letters is the default.
        ''',
    )
    parser.add_argument(
        '--digits',
        action='store_true',
        help='''
        Include digits 0-9 in the password.
        ''',
    )
    parser.add_argument(
        '--hex',
        action='store_true',
        help='''
        Include 0-9, a-f in the password.
        ''',
    )
    parser.add_argument(
        '--binary',
        action='store_true',
        help='''
        Include 0, 1 in the password.
        ''',
    )
    parser.add_argument(
        '--punctuation',
        action='store_true',
        help='''
        Include punctuation symbols in the password.
        ''',
    )
    parser.add_argument(
        '--prefix',
        type=str,
        default=None,
        help='''
        Add a static prefix to the password.
        ''',
    )
    parser.add_argument(
        '--suffix',
        type=str,
        default=None,
        help='''
        Add a static suffix to the password.
        ''',
    )
    parser.add_argument(
        '--lower',
        action='store_true',
        help='''
        Convert the entire password to lowercase.
        ''',
    )
    parser.add_argument(
        '--upper',
        action='store_true',
        help='''
        Convert the entire password to uppercase.
        ''',
    )
    parser.set_defaults(func=passwordy_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
