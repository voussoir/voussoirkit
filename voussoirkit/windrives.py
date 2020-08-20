'''
NOTE: I have not yet figured out how to get a list of volumes that are mounted
to folders instead of drive letters. I think this is the API I need:
https://docs.microsoft.com/en-us/windows/win32/fileio/enumerating-volume-mount-points
'''
import ctypes
import string

def get_drive_info(letter):
    '''
    Given a drive letter, return a dictionary containing its attributes.

    Thanks Nicholas Orlowski
    http://stackoverflow.com/a/12056414
    '''
    kernel32 = ctypes.windll.kernel32
    name_buffer = ctypes.create_unicode_buffer(1024)
    filesystem_buffer = ctypes.create_unicode_buffer(1024)
    serial_number = None
    max_component_length = None
    file_system_flags = None

    letter = letter.rstrip(':\\/')
    drive_active = kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(f'{letter}:\\'),
        name_buffer,
        ctypes.sizeof(name_buffer),
        serial_number,
        max_component_length,
        file_system_flags,
        filesystem_buffer,
        ctypes.sizeof(filesystem_buffer),
    )
    info = {
        'active': bool(drive_active),
        'filesystem': filesystem_buffer.value,
        'name': name_buffer.value,
    }
    return info

def get_drive_letters():
    '''
    Return a list of all connected drive letters.

    Thanks RichieHindle
    http://stackoverflow.com/a/827398

    "If the function succeeds, the return value is a bitmask representing the
    currently available disk drives. Bit position 0 (the least-significant bit)
    is drive A, bit position 1 is drive B, bit position 2 is drive C, and so on."
    https://docs.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlogicaldrives
    '''
    letters = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            letters.append(letter)
        bitmask >>= 1
    return letters

def get_drive_letter_by_name(name):
    '''
    Given the name of a drive (the user-customizable name seen in Explorer),
    return the letter of that drive.

    Raises KeyError if it is not found.
    '''
    drives = get_drive_map()
    for (letter, info) in drives.items():
        if info['name'] == name:
            return letter
    raise KeyError(name)

def get_drive_map():
    '''
    Return a dict of {letter: info}.
    '''
    drives = {letter: get_drive_info(letter) for letter in get_drive_letters()}
    return drives
