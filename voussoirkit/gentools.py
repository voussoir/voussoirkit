import itertools

def chunk_generator(sequence, chunk_length):
    '''
    Given any sequence input, yield lists of length <= `chunk_length`.

    Note: this generator always yields lists, even if the input was a string.
    I don't want to deal with special cases of types that return differently.
    '''
    iterator = iter(sequence)
    while True:
        chunk = list(itertools.islice(iterator, chunk_length))
        if not chunk:
            break
        yield chunk
