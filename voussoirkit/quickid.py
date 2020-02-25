'''
This module is designed to provide a GOOD ENOUGH means of identifying duplicate
files very quickly, so that more in-depth checks can be done on likely matches.
'''

import hashlib
import os
import sys

SEEK_END = 2
CHUNK_SIZE = 2**20
FORMAT = '{size}_{hashtype}_{chunk_size}_{hash}'

def equal_handle(handle1, handle2, *args, **kwargs):
    size1 = handle1.seek(0, SEEK_END)
    size2 = handle2.seek(0, SEEK_END)
    handle1.seek(0)
    handle2.seek(0)
    if size1 != size2:
        return False
    id1 = quickid_handle(handle1, *args, **kwargs)
    id2 = quickid_handle(handle2, *args, **kwargs)
    return id1 == id2

def equal_file(filename1, filename2, *args, **kwargs):
    filename1 = os.path.abspath(filename1)
    filename2 = os.path.abspath(filename2)
    with open(filename1, 'rb') as handle1, open(filename2, 'rb') as handle2:
        return equal_handle(handle1, handle2, *args, **kwargs)

def quickid_handle(handle, chunk_size=None):
    if chunk_size is None:
        chunk_size = CHUNK_SIZE

    hashtype = 'md5'
    hasher = hashlib.md5()
    size = handle.seek(0, SEEK_END)
    handle.seek(0)

    if size <= 2 * chunk_size:
        hasher.update(handle.read())
    else:
        hasher.update(handle.read(chunk_size))
        handle.seek(-1 * chunk_size, SEEK_END)
        hasher.update(handle.read())

    output = FORMAT.format(
        size=size,
        hashtype=hashtype,
        chunk_size=chunk_size,
        hash=hasher.hexdigest(),
    )
    return output

def quickid_file(filename, *args, **kwargs):
    filename = os.path.abspath(filename)
    with open(filename, 'rb') as handle:
        return quickid_handle(handle, *args, **kwargs)

def main(argv):
    print(quickid_file(argv[0]))

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
