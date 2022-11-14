'''
This module provides integer constants for power-of-two byte size units, and
functions for converting between ints and human-readable strings. E.g.:
bytestring.bytestring(5000000) -> '4.768 MiB'
bytestring.parsebytes('8.5gb') -> 9126805504
'''
import argparse
import re
import sys

from voussoirkit import betterhelp
from voussoirkit import pipeable

BYTE = 1
KIBIBYTE = 1024 * BYTE
MEBIBYTE = 1024 * KIBIBYTE
GIBIBYTE = 1024 * MEBIBYTE
TEBIBYTE = 1024 * GIBIBYTE
PEBIBYTE = 1024 * TEBIBYTE
EXIBYTE = 1024 * PEBIBYTE
ZEBIBYTE = 1024 * EXIBYTE
YOBIBYTE = 1024 * ZEBIBYTE

BYTE_STRING = 'b'
KIBIBYTE_STRING = 'KiB'
MEBIBYTE_STRING = 'MiB'
GIBIBYTE_STRING = 'GiB'
TEBIBYTE_STRING = 'TiB'
PEBIBYTE_STRING = 'PiB'
EXIBYTE_STRING = 'EiB'
ZEBIBYTE_STRING = 'ZiB'
YOBIBYTE_STRING = 'YiB'

# backwards compatibility for a typo that survived way too long.
MIBIBYTE = MEBIBYTE
MIBIBYTE_STRING = MEBIBYTE_STRING

UNIT_STRINGS = {
    BYTE: BYTE_STRING,
    KIBIBYTE: KIBIBYTE_STRING,
    MEBIBYTE: MEBIBYTE_STRING,
    GIBIBYTE: GIBIBYTE_STRING,
    TEBIBYTE: TEBIBYTE_STRING,
    PEBIBYTE: PEBIBYTE_STRING,
    EXIBYTE: EXIBYTE_STRING,
    ZEBIBYTE: ZEBIBYTE_STRING,
    YOBIBYTE: YOBIBYTE_STRING,
}

REVERSED_UNIT_STRINGS = {value: key for (key, value) in UNIT_STRINGS.items()}
UNIT_SIZES = sorted(UNIT_STRINGS.keys(), reverse=True)

class BytestringException(Exception):
    pass

class ParseError(BytestringException, ValueError):
    pass

def bytestring(size, decimal_places=3, force_unit=None, thousands_separator=False):
    '''
    Convert a number into a string like "100 MiB".

    >>> bytestring(1000)
    '1000 b'
    >>> bytestring(1024)
    '1.000 KiB'
    >>> bytestring(123456)
    '120.562 KiB'
    >>> bytestring(800000000)
    '762.939 MiB'
    >>> bytestring(800000000, decimal_places=0)
    '763 MiB'
    >>> bytestring(100000000, force_unit=KIBIBYTE, thousands_separator=True)
    '97,656.250 KiB'

    decimal_places:
        The number of digits after the decimal, including trailing zeros,
        for all divisors except bytes.

    force_unit:
        You can provide one of the size constants to force that divisor.
        If None, an appropriate size unit is chosen automatically.

    thousands_separator:
        If True, the strings will have thousands separators.
    '''
    if force_unit is None:
        divisor = get_appropriate_divisor(size)
    else:
        if isinstance(force_unit, str):
            force_unit = normalize_unit_string(force_unit)
            force_unit = REVERSED_UNIT_STRINGS[force_unit]
        divisor = force_unit

    size_unit_string = UNIT_STRINGS[divisor]

    if divisor == BYTE:
        decimal_places = 0

    if thousands_separator:
        size_string = '{number:,.0{decimal_places}f} {unit}'
    else:
        size_string = '{number:.0{decimal_places}f} {unit}'

    size_string = size_string.format(
        decimal_places=decimal_places,
        number=size/divisor,
        unit=size_unit_string,
    )
    return size_string

def get_appropriate_divisor(size):
    '''
    Return the divisor that would be appropriate for displaying this byte size.

    >>> get_appropriate_divisor(1000)
    1
    >>> get_appropriate_divisor(1024)
    1024
    >>> get_appropriate_divisor(123456789)
    1048576
    '''
    size = abs(size)
    for unit in UNIT_SIZES:
        if size >= unit:
            appropriate_unit = unit
            break
    else:
        appropriate_unit = 1
    return appropriate_unit

def normalize_unit_string(string):
    '''
    Given a string "k" or "kb" or "kib" in any case, return "KiB", etc.
    '''
    string = string.lower().strip()
    for (size, unit_string) in UNIT_STRINGS.items():
        unit_string_l = unit_string.lower()
        if string in (unit_string_l, unit_string_l[0], unit_string_l.replace('i', '')):
            return unit_string
    raise ParseError(f'Unrecognized unit string "{string}".')

def parsebytes(string):
    '''
    Given a string like "100 kib", return the appropriate integer value.
    Accepts "k", "kb", "kib" in any casing.
    '''
    string = string.lower().strip()
    string = string.replace(',', '')

    matches = re.findall(r'[\d\.-]+', string)
    if len(matches) == 0:
        raise ParseError('No numbers found.')
    if len(matches) > 1:
        raise ParseError('Too many numbers found.')
    number = matches[0]

    if not string.startswith(number):
        raise ParseError('Number is not at start of string.')

    number_string = number

    try:
        number = float(number)
    except ValueError as exc:
        raise ParseError(number) from exc

    # if the string has no text besides the number, treat it as int of bytes.
    unit_string = string.replace(number_string, '')
    if unit_string == '':
        return int(number)

    unit_string = normalize_unit_string(unit_string)
    multiplier = REVERSED_UNIT_STRINGS[unit_string]

    return int(number * multiplier)

def bytestring_argparse(args):
    numbers = pipeable.input_many(args.numbers, strip=True, skip_blank=True)
    for number in numbers:
        try:
            number = int(number)
            pipeable.stdout(bytestring(number))
        except ValueError:
            pipeable.stdout(parsebytes(number))
    return 0

def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        Converts integers into byte strings and back again.
        ''',
    )
    parser.examples = [
        {'args': '10000', 'run': True},
        {'args': '123456789', 'run': True},
        {'args': '999999999999 888888888 890', 'run': True},
        {'args': ['800 gb'], 'run': True},
        {'args': ['9.2 kib', '100kb', '42b'], 'run': True},
    ]

    parser.add_argument(
        'numbers',
        nargs='+',
        help='''
        Uses pipeable to support !c clipboard, !i stdin, which should be one
        number per line.
        ''',
    )
    parser.set_defaults(func=bytestring_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
