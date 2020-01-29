'''
On Windows, square brackets do not have a special meaning in glob strings.
However, python's glob module is written for unix-style globs in which brackets
represent character classes / ranges.

On Windows we should escape those brackets to get the right results.
But calling glob.escape would also escape asterisk which may not be desired.
So this module just provides a modified version of glob.glob which will escape
only square brackets when called on windows, and behave normally on linux.
'''
import fnmatch as python_fnmatch
import glob as python_glob
import os
import re

def fix(pattern):
    if os.name == 'nt':
        pattern = re.sub(r'(\[|\])', r'[\1]', pattern)
    return pattern

def glob(pathname, *, recursive=False):
    return python_glob.glob(fix(pathname), recursive=recursive)

def fnmatch(name, pat):
    return python_fnmatch.fnmatch(name, fix(pat))
