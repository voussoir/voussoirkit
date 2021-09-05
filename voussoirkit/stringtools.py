import re
import typing
import unicodedata

from voussoirkit import sentinel

TRUTHYSTRING_TRUE = {s.lower() for s in ('1', 'true', 't', 'yes', 'y', 'on')}
TRUTHYSTRING_FALSE = {s.lower() for s in ('0', 'false', 'f', 'no', 'n', 'off')}
TRUTHYSTRING_NONE = {s.lower() for s in ('null', 'none')}
TRUTHYSTRING_NO_FALLBACK = sentinel.Sentinel('no fallback')

def collapse_whitespace(text) -> str:
    '''
    Replace all whitespace sequences with a single space and strip the ends.
    '''
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def comma_space_split(text) -> list:
    '''
    Split the string by commas and spaces, discarding all extra
    whitespace and blank parts.

    >>> comma_space_split('a b, c,,d')
    ['a', 'b', 'c', 'd']
    '''
    if text is None:
        return text
    return re.split(r'[ ,]+', text.strip())

def excise(text, mark_left, mark_right) -> str:
    '''
    Remove the text between the left and right landmarks, including the
    landmarks themselves, and return the rest of the text.

    excise('What a wonderful day [soundtrack].mp3', ' [', ']') ->
    returns 'What a wonderful day.mp3'
    '''
    if mark_left in text and mark_right in text:
        return text.split(mark_left, 1)[0] + text.rsplit(mark_right, 1)[-1]
    return text

def natural_sorter(s):
    '''
    This function is used as the `key` argument in
    list.sort(key=stringtools.natural_sorter).

    Used for sorting strings in 'natural' order instead of lexicographic order,
    so that you get 1 2 3 4 5 6 7 8 9 10 11 12 13 ...
    instead of 1 10 11 12 13 2 3 4 5 ...

    Thank you Mark Byers
    http://stackoverflow.com/a/11150413
    '''
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return alphanum_key(s)

def pascal_to_loudsnakes(text) -> str:
    '''
    >>> pascal_to_loudsnakes('PascalCase')
    'PASCAL_CASE'
    >>> pascal_to_loudsnakes('HTMLDocument')
    'HTML_DOCUMENT'
    '''
    text = re.sub(r'([a-z])([A-Z])', r'\1_\2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', text)
    text = text.upper()
    return text

def remove_characters(text, characters) -> str:
    translator = {ord(c): None for c in characters}
    text = text.translate(translator)
    return text

def remove_control_characters(text) -> str:
    '''
    Thanks Alex Quinn
    https://stackoverflow.com/a/19016117

    unicodedata.category(character) returns some two-character string
    where if [0] is a C then the character is a control character.
    '''
    return ''.join(c for c in text if unicodedata.category(c)[0] != 'C')

def title_capitalize(text) -> str:
    text = text.strip().title()
    articles = [
        'a',
        'an',
        'and',
        'at',
        'for',
        'from',
        'in',
        'of',
        'on',
        'the',
        'to',
    ]
    for article in articles:
        text = re.sub(rf' {article}\b', f' {article.lower()}', text, flags=re.IGNORECASE)

    text = text.replace('\'S', '\'s')

    # Roman numerals. Not handling L, M yet because I don't want to mess up
    # real words like "mix", but let's take a look at expanding this in
    # the future.
    text = re.sub(r'(\b[ivx]+\b)', lambda m: m.group(1).upper(), text, flags=re.IGNORECASE)
    return text

def truthystring(
        s,
        fallback=TRUTHYSTRING_NO_FALLBACK,
        strict_int=True,
        true_set=TRUTHYSTRING_TRUE,
        false_set=TRUTHYSTRING_FALSE,
        none_set=TRUTHYSTRING_NONE,
    ) -> typing.Union[bool, None]:
    '''
    If s is already a boolean, int, or None, return a boolean or None.
    If strict_int is True, only integers 0 and 1 will be coerced to boolean,
    and other integers will return the fallback or raise ValueError.

    If s is a string, return True, False, or None based on the options presented
    in true_set, false_set, none_set where s is treated case-insensitively.

    If s is not in any of those sets and a fallback is provided,
    return the fallback.

    If there is no fallback, raise ValueError.
    '''
    if s is None:
        return None

    if isinstance(s, bool):
        return s

    if isinstance(s, int):
        if (strict_int is False) or (s in {0, 1}):
            return bool(s)

    if isinstance(s, str):
        s_lower = s.lower()
        if s_lower in true_set:
            return True
        if s_lower in false_set:
            return False
        if s_lower in none_set:
            return None

    if fallback is TRUTHYSTRING_NO_FALLBACK:
        raise ValueError(s)

    return fallback
