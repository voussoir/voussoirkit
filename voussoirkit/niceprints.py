'''
niceprints
==========

This module provides functions which add visual flair to your text, to make
your print statements more interesting.

These functions only do the minimum amount of transformation for their effect.
You should do your uppercase/lowercase, text wrap, etc. before calling
these functions.
'''
import shutil

from voussoirkit import dotdict

SINGLE_BOX = dotdict.DotDict(
    upper_left='┌',
    upper_right='┐',
    top='─',
    lower_left='└',
    lower_right='┘',
    side='│',
)

DOUBLE_BOX = dotdict.DotDict(
    upper_left='╔',
    upper_right='╗',
    top='═',
    lower_left='╚',
    lower_right='╝',
    side='║',
)

def equals_header(text):
    '''
    Sample text
    ===========
    '''
    return text + '\n' + ('=' * len(text))

def in_box(text, *, boxchars=SINGLE_BOX, title=''):
    '''
    ┌───────────┐
    │Sample text│
    └───────────┘
    ╔═══════════╗
    ║Sample text║
    ╚═══════════╝
    ┌Sample Title────────────────────────────────┐
    │There is breaking news about an urgent topic│
    │and you'll never guess what it is           │
    └────────────────────────────────────────────┘
    '''
    lines = text.splitlines()
    longest_line = max(max(len(line) for line in lines), len(title))
    top = title + boxchars.top * (longest_line - len(title))
    bottom = boxchars.top * longest_line

    new_lines = []
    new_lines.append(boxchars.upper_left + top + boxchars.upper_right)
    for line in lines:
        new_lines.append(boxchars.side + line.ljust(longest_line, ' ') + boxchars.side)
    new_lines.append(boxchars.lower_left + bottom + boxchars.lower_right)
    return '\n'.join(new_lines)

def solid_hash_header(text):
    '''
    # Sample text ##############################################################
    '''
    cli_width = shutil.get_terminal_size()[0]
    # One left hash, space, and space after text.
    right_count = cli_width - (len(text) + 3)
    right_hashes = '#' * right_count
    return f'# {text} {right_hashes}'
