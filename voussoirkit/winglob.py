'''
On Windows, square brackets do not have a special meaning in glob strings.
However, python's glob module is written for unix-style globs in which brackets
represent character classes / ranges.

Calling glob.escape would also escape asterisk which may not be desired.
So this module just provides a modified version of glob.glob which will escape
only square brackets when called on windows, and behave normally on linux.
'''
import glob as python_glob
import os
import re

def glob(pattern):
    if os.name == 'nt':
        pattern = re.sub(r'(\[|\])', r'[\1]', pattern)
    return python_glob.glob(pattern)
