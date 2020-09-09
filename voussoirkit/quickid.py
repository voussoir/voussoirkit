'''
This module is designed to provide a GOOD ENOUGH means of identifying duplicate
files very quickly, so that more in-depth checks can be done on likely matches.
'''
import hashlib
import os
import sys

from voussoirkit import pathclass

SEEK_END = 2
CHUNK_SIZE = 2**20
FORMAT = '{size}_{hashtype}_{chunk_size}_{hash}'

HASH_CLASSES = {
    name: getattr(hashlib, name)
    for name in hashlib.algorithms_guaranteed
}

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
    filename1 = pathclass.Path(filename1).absolute_path
    filename2 = pathclass.Path(filename2).absolute_path
    if os.path.getsize(filename1) != os.path.getsize(filename2):
        return False
    with open(filename1, 'rb') as handle1, open(filename2, 'rb') as handle2:
        return equal_handle(handle1, handle2, *args, **kwargs)

def matches_handle(handle, other_id):
    (other_size, hashtype, chunk_size, other_hash) = other_id.split('_')
    other_size = int(other_size)
    chunk_size = int(chunk_size)

    this_size = handle.seek(0, SEEK_END)
    handle.seek(0)
    if this_size != other_size:
        return False

    this_id = quickid_handle(handle, hashtype=hashtype, chunk_size=chunk_size)
    return this_id == other_id

def matches_file(filename, other_id):
    filename = pathclass.Path(filename).absolute_path
    with open(filename, 'rb') as handle:
        return matches_handle(handle, other_id)

def quickid_handle(handle, hashtype='md5', chunk_size=None):
    if chunk_size is None:
        chunk_size = CHUNK_SIZE

    hasher = HASH_CLASSES[hashtype]()
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
    filename = pathclass.Path(filename).absolute_path
    with open(filename, 'rb') as handle:
        return quickid_handle(handle, *args, **kwargs)

def main(argv):
    print(quickid_file(argv[0]))

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
