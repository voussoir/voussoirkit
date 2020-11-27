import re
import unicodedata

def collapse_whitespace(text):
    '''
    Replace all whitespace sequences with a single space and strip the ends.
    '''
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def comma_space_split(text):
    '''
    Split the string by commas and spaces, discarding all extra
    whitespace and blank parts.

    'a b, c,,d' -> ['a', 'b', 'c', 'd']
    '''
    if text is None:
        return text
    return re.split(r'[ ,]+', text.strip())

def excise(text, mark_left, mark_right):
    '''
    Remove the text between the left and right landmarks, including the
    landmarks themselves, and return the rest of the text.

    excise('What a wonderful day [soundtrack].mp3', ' [', ']') ->
    returns 'What a wonderful day.mp3'
    '''
    if mark_left in text and mark_right in text:
        return text.split(mark_left, 1)[0] + text.rsplit(mark_right, 1)[-1]
    return text

def pascal_to_loudsnakes(text):
    '''
    PascalCase -> PASCAL_CASE
    HTMLDocument -> HTML_DOCUMENT
    '''
    text = re.sub(r'([a-z])([A-Z])', r'\1_\2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', text)
    text = text.upper()
    return text

def remove_characters(text, characters):
    translator = {ord(c): None for c in characters}
    text = text.translate(translator)
    return text

def remove_control_characters(text):
    '''
    Thanks Alex Quinn
    https://stackoverflow.com/a/19016117

    unicodedata.category(character) returns some two-character string
    where if [0] is a C then the character is a control character.
    '''
    return ''.join(c for c in text if unicodedata.category(c)[0] != 'C')

def title_capitalize(text):
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
