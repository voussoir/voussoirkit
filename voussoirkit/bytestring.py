'''
This module provides integer constants for power-of-two byte size units, and
functions for converting between ints and human-readable strings e.g. "1.2 GiB".
'''
import re
import sys

from voussoirkit import pipeable

BYTE = 1
KIBIBYTE = 1024 * BYTE
MIBIBYTE = 1024 * KIBIBYTE
GIBIBYTE = 1024 * MIBIBYTE
TEBIBYTE = 1024 * GIBIBYTE
PEBIBYTE = 1024 * TEBIBYTE
EXIBYTE = 1024 * PEBIBYTE
ZEBIBYTE = 1024 * EXIBYTE
YOBIBYTE = 1024 * ZEBIBYTE

BYTE_STRING = 'b'
KIBIBYTE_STRING = 'KiB'
MIBIBYTE_STRING = 'MiB'
GIBIBYTE_STRING = 'GiB'
TEBIBYTE_STRING = 'TiB'
PEBIBYTE_STRING = 'PiB'
EXIBYTE_STRING = 'EiB'
ZEBIBYTE_STRING = 'ZiB'
YOBIBYTE_STRING = 'YiB'

UNIT_STRINGS = {
    BYTE: BYTE_STRING,
    KIBIBYTE: KIBIBYTE_STRING,
    MIBIBYTE: MIBIBYTE_STRING,
    GIBIBYTE: GIBIBYTE_STRING,
    TEBIBYTE: TEBIBYTE_STRING,
    PEBIBYTE: PEBIBYTE_STRING,
    EXIBYTE: EXIBYTE_STRING,
    ZEBIBYTE: ZEBIBYTE_STRING,
    YOBIBYTE: YOBIBYTE_STRING,
}
REVERSED_UNIT_STRINGS = {value: key for (key, value) in UNIT_STRINGS.items()}
UNIT_SIZES = sorted(UNIT_STRINGS.keys(), reverse=True)


def bytestring(size, decimal_places=3, force_unit=None):
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

    force_unit:
        If None, an appropriate size unit is chosen automatically.
        Otherwise, you can provide one of the size constants to force that divisor.
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
    For example:
        1000 => 1 to display 1,000 b
        1024 => 1024 to display 1 KiB
        123456789 => 1048576 to display 117.738 MiB
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
    string = string.lower()
    for (size, unit_string) in UNIT_STRINGS.items():
        unit_string_l = unit_string.lower()
        if string in (unit_string_l, unit_string_l[0], unit_string_l.replace('i', '')):
            return unit_string
    raise ValueError(f'Unrecognized unit string "{string}".')

def parsebytes(string):
    '''
    Given a string like "100 kib", return the appropriate integer value.
    Accepts "k", "kb", "kib" in any casing.
    '''
    string = string.lower().strip()
    string = string.replace(' ', '').replace(',', '')

    matches = re.findall(r'[\d\.-]+', string)
    if len(matches) == 0:
        raise ValueError('No numbers found.')
    if len(matches) > 1:
        raise ValueError('Too many numbers found.')
    number = matches[0]

    if not string.startswith(number):
        raise ValueError('Number is not at start of string.')

    # if the string has no text besides the number, return that int of bytes.
    unit_string = string.replace(number, '')
    if unit_string == '':
        return int(float(number))

    number = float(number)
    unit_string = normalize_unit_string(unit_string)
    multiplier = REVERSED_UNIT_STRINGS[unit_string]

    return int(number * multiplier)

def main(argv):
    for line in pipeable.go(argv, strip=True, skip_blank=True):
        n = int(line)
        pipeable.output(bytestring(n))

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
