'''
passwordy
=========

This module provides functions for generating random strings.

Command line usage:

> passwordy <length> [flags]

length:
    Integer number of characters, or words when using sentence mode.

# Sentence mode:
--sentence:
    If this argument is passed, `length` random words are chosen.
    Only --separator, --upper, and --lower can be used in sentence mode.

--separator <string>:
    When using sentence mode, the words will be joined with this string.

# urandom mode:
--urandom:
    If this argument is passed, os.urandom is called for cryptographically
    strong randomness and the password is shown as hex.
    Only --upper and --lower can be used in urandom mode (though the hex is
    lowercase by default).

# Normal mode:
--letters:
    Include ASCII letters in the password.
    If none of the other following options are chosen, letters is the default.

--digits:
    Include digits 0-9 in the password.

--hex
    Include 0-9, a-f in the password.

--binary
    Include 0, 1 in the password.

--punctuation
    Include punctuation symbols in the password.

--upper
    Convert the entire password to uppercase.

--lower
    Convert the entire password to lowercase.
'''
import argparse
import math
import os
import random
import string
import sys

from voussoirkit import betterhelp
from voussoirkit import pipeable

def make_password(
        length,
        letters=False,
        digits=False,
        hex=False,
        binary=False,
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

    return ''.join(random.choices(tuple(alphabet), k=length))

def make_sentence(length, separator=' '):
    '''
    Returns a string containing `length` words, which come from
    dictionary.common.
    '''
    import dictionary.common as common
    words = random.choices(common.words, k=length)
    words = [w.replace(' ', separator) for w in words]
    result = separator.join(words)
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

def passwordy_argparse(args):
    if args.sentence:
        password = make_sentence(args.length, args.separator)
    elif args.urandom:
        password = urandom_hex(args.length)
    else:
        if not any([args.letters, args.digits, args.hex, args.binary, args.punctuation]):
            letters = True
        else:
            letters = args.letters
        password = make_password(
            length=args.length,
            letters=letters,
            digits=args.digits,
            hex=args.hex,
            binary=args.binary,
            punctuation=args.punctuation,
        )
    if args.lower:
        password = password.lower()
    elif args.upper:
        password = password.upper()
    pipeable.stdout(password)
    return 0

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('length', type=int)
    parser.add_argument('--urandom', action='store_true')
    parser.add_argument('--sentence', action='store_true')
    parser.add_argument('--separator', nargs='?', default=' ')
    parser.add_argument('--letters', action='store_true')
    parser.add_argument('--digits', action='store_true')
    parser.add_argument('--hex', action='store_true')
    parser.add_argument('--binary', action='store_true')
    parser.add_argument('--punctuation', action='store_true')
    parser.add_argument('--lower', action='store_true')
    parser.add_argument('--upper', action='store_true')
    parser.set_defaults(func=passwordy_argparse)

    return betterhelp.single_main(argv, parser, __doc__)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
