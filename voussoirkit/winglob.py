'''
On Windows, square brackets do not have a special meaning in glob strings.
However, python's glob module is written for unix-style globs in which brackets
represent character classes / ranges.

On Windows we should escape those brackets to get results that are consistent
with a Windows user's expectations. But calling glob.escape would also escape
asterisk which may not be desired. So this module just provides a modified
version of glob.glob which will escape only square brackets when called on
Windows, and behave normally on Linux.
'''
import fnmatch as python_fnmatch
import glob as python_glob
import os
import re

if os.name == 'nt':
    GLOB_SYMBOLS = {'*', '?'}
else:
    GLOB_SYMBOLS = {'*', '?', '['}

def fix(pattern):
    if os.name == 'nt':
        pattern = re.sub(r'(\[|\])', r'[\1]', pattern)
    return pattern

def fnmatch(name, pat):
    return python_fnmatch.fnmatch(name, fix(pat))

def fnmatch_filter(names, pat):
    return python_fnmatch.filter(names, fix(pat))

def glob(pathname, *, recursive=False):
    return python_glob.glob(fix(pathname), recursive=recursive)

def glob_many(patterns, *, recursive=False):
    '''
    Given many glob patterns, yield the results as a single generator.
    Saves you from having to write the nested loop.
    '''
    for pattern in patterns:
        yield from glob(pattern, recursive=recursive)

def is_glob(pattern):
    '''
    Improvements can be made to validate [] ranges for unix, but properly
    parsing the range syntax is not something I'm interested in doing right now
    and it would become the largest function in the whole module.
    '''
    return len(set(pattern).intersection(GLOB_SYMBOLS)) > 0
