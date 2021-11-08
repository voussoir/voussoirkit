'''
bencode
=======

This module provides the functions bencode and bdecode for working with
Bencode data.

https://en.wikipedia.org/wiki/Bencode
'''
# PUBLIC
####################################################################################################

def bencode(data) -> bytes:
    '''
    Encode python types to bencode.
    '''
    data_type = type(data)

    encoders = {
        bytes: _encode_bytes,
        int: _encode_int,
        dict: _encode_dict,
        tuple: _encode_list,
        list: _encode_list,
    }

    encoder = encoders.get(data_type, None)
    if encoder is None:
        raise TypeError(f'Invalid data type {data_type}.')

    return encoder(data)

def bdecode(data):
    '''
    Decode bencode to python types.
    '''
    return _decode(data, start_index=0)['result']

# INTERNALS
################################################################################

def _encode_bytes(data):
    '''
    Binary data is encoded as {length}:{bytes}.
    '''
    return b'%d:%s' % (len(data), data)

def _encode_dict(data):
    '''
    Dicts are encoded as d{key}{value}{key}{value}e with the keys in
    lexicographic order.
    Keys must be byte strings
    '''
    result = []
    keys = sorted(data.keys())
    for key in keys:
        result.append(bencode(key))
        result.append(bencode(data[key]))
    result = b''.join(result)
    return b'd%se' % result

def _encode_int(data):
    '''
    Integers are encoded as i{integer}e.
    '''
    return b'i%de' % data

def _encode_list(data):
    '''
    Lists are encoded as l{item}{item}{item}e.
    '''
    result = []
    for item in data:
        result.append(bencode(item))
    result = b''.join(result)
    return b'l%se' % result

def _decode(data, *, start_index):
    if not isinstance(data, bytes):
        raise TypeError(f'bencode data should be bytes, not {type(data)}.')

    identifier = data[start_index:start_index+1]
    if identifier == b'i':
        ret = _decode_int(data, start_index=start_index)

    elif identifier.isdigit():
        ret = _decode_bytes(data, start_index=start_index)

    elif identifier == b'l':
        ret = _decode_list(data, start_index=start_index)

    elif identifier == b'd':
        ret = _decode_dict(data, start_index=start_index)

    else:
        raise ValueError(f'Invalid initial delimiter "{identifier}".')

    return ret

def _decode_bytes(data, *, start_index):
    colon = data.find(b':', start_index)
    if colon == -1:
        raise ValueError('Missing bytes delimiter ":"')

    start = colon + 1
    length = int(data[start_index:colon])
    end = start + length

    text = data[start:end]

    return {'result': text, 'remainder_index': end}

def _decode_dict(data, *, start_index):
    result = {}

    # +1 to skip the leading d.
    start_index += 1

    # We need to check a slice of length 1 because subscripting into bytes
    # returns ints.
    while data[start_index:start_index+1] != b'e':
        temp = _decode(data, start_index=start_index)
        key = temp['result']
        start_index = temp['remainder_index']

        temp = _decode(data, start_index=start_index)
        value = temp['result']
        start_index = temp['remainder_index']

        result[key] = value

    # +1 to skip the trailing e.
    return {'result': result, 'remainder_index': start_index+1}

def _decode_int(data, *, start_index):
    # +1 to skip the leading i.
    start_index += 1

    end = data.find(b'e', start_index)
    if end == -1:
        raise ValueError('Missing end delimiter "e"')

    result = int(data[start_index:end])

    # +1 to skip the trailing e.
    return {'result': result, 'remainder_index': end+1}

def _decode_list(data, *, start_index):
    # +1 to skip the leading l.
    start_index += 1

    result = []

    # We need to check a slice of length 1 because subscripting into bytes
    # returns ints.
    while data[start_index:start_index+1] != b'e':
        item = _decode(data, start_index=start_index)
        result.append(item['result'])
        start_index = item['remainder_index']

    # +1 to skip the trailing e.
    return {'result': result, 'remainder_index': start_index+1}
