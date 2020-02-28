def bencode(data):
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
        raise ValueError(f'Invalid data type {data_type}.')
    return encoder(data)

def bdecode(data):
    '''
    Decode bencode to python types.
    '''
    return _decode(data)['result']

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
    keys = list(data.keys())
    keys.sort()
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

def _decode(data):
    if not isinstance(data, bytes):
        raise TypeError(f'bencode data should be bytes, not {type(data)}.')

    identifier = data[0:1]
    if identifier == b'i':
        ret = _decode_int(data)

    elif identifier.isdigit():
        ret = _decode_bytes(data)

    elif identifier == b'l':
        ret = _decode_list(data)

    elif identifier == b'd':
        ret = _decode_dict(data)

    else:
        raise ValueError(f'Invalid initial delimiter "{identifier}".')

    return ret

def _decode_bytes(data):
    colon = data.find(b':')

    start = colon + 1
    size = int(data[:colon])
    end = start + size

    text = data[start:end]
    remainder = data[end:]

    return {'result': text, 'remainder': remainder}

def _decode_dict(data):
    result = {}

    # slice leading d
    remainder = data[1:]

    # Checking [0:1] instead of [0] because [0] returns an int!!!!
    # [0:1] returns b'e' which I want.
    while remainder[0:1] != b'e':
        temp = _decode(remainder)
        key = temp['result']
        remainder = temp['remainder']

        temp = _decode(remainder)
        value = temp['result']
        remainder = temp['remainder']
        result[key] = value

    # slice ending e
    remainder = remainder[1:]
    return {'result': result, 'remainder': remainder}

def _decode_int(data):
    # slide leading i
    data = data[1:]

    end = data.find(b'e')
    if end == -1:
        raise ValueError('Missing end delimiter "e"')
    result = int(data[:end])

    # slice ending e
    remainder = data[end+1:]
    return {'result': result, 'remainder': remainder}

def _decode_list(data):
    result = []

    # slice leading l
    remainder = data[1:]

    while remainder[0:1] != b'e':
        item = _decode(remainder)
        result.append(item['result'])
        remainder = item['remainder']

    # slice ending e
    remainder = remainder[1:]
    return {'result': result, 'remainder': remainder}
