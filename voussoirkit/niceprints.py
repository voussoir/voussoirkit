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
from voussoirkit import stringtools

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
    return text + '\n' + ('=' * stringtools.unicode_width(text))

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

    This function does not perform text wrapping. Wrap your text before putting
    it in the box.
    '''
    lines = text.splitlines()
    widths = {line: stringtools.unicode_width(line) for line in lines}
    if len(widths) == 0:
        longest_line = 0
    else:
        longest_line = max(widths.values())

    box_width = max(longest_line, stringtools.unicode_width(title))
    top = title + boxchars.top * (box_width - stringtools.unicode_width(title))
    bottom = boxchars.top * box_width

    new_lines = []
    new_lines.append(boxchars.upper_left + top + boxchars.upper_right)
    for line in lines:
        space_needed = box_width - widths[line]
        space = ' ' * space_needed
        new_lines.append(f'{boxchars.side}{line}{space}{boxchars.side}')
    new_lines.append(boxchars.lower_left + bottom + boxchars.lower_right)
    return '\n'.join(new_lines)

def solid_hash_header(text):
    '''
    # Sample text ##############################################################
    '''
    cli_width = shutil.get_terminal_size()[0]
    # One left hash, space, and space after text.
    right_count = cli_width - (stringtools.unicode_width(text) + 3)
    right_hashes = '#' * right_count
    return f'# {text} {right_hashes}'
