'''
This module is designed to provide a GOOD ENOUGH means of identifying duplicate
files very quickly, so that more in-depth checks can be done on likely matches.
'''
import hashlib
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
    '''
    Given two handles, return True if they have the same quickid hash.
    '''
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
    '''
    Given two files, return True if they have the same quickid hash.
    '''
    file1 = pathclass.Path(filename1)
    file2 = pathclass.Path(filename2)
    file1.assert_is_file()
    file2.assert_is_file()
    if file1.size != file2.size:
        return False
    with file1.open('rb') as handle1, file2.open('rb') as handle2:
        return equal_handle(handle1, handle2, *args, **kwargs)

def matches_handle(handle, other_id):
    '''
    Given a handle and a quickid hash, return True if the handle matches
    that hash.
    '''
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
    '''
    Given a file and a quickid hash, return True if the file matches
    that hash.
    '''
    file = pathclass.Path(filename)
    with file.open('rb') as handle:
        return matches_handle(handle, other_id)

def quickid_handle(handle, hashtype='md5', chunk_size=CHUNK_SIZE):
    '''
    Return the quickid hash for this handle.
    '''
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
    '''
    Return the quickid hash for this file.
    '''
    file = pathclass.Path(filename)
    file.assert_is_file()
    with file.open('rb') as handle:
        return quickid_handle(handle, *args, **kwargs)

def main(argv):
    print(quickid_file(argv[0]))

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
