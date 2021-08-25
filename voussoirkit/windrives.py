'''
This module provides functions for getting information about logical drives
on Windows.
'''
import ctypes
import re
import string
import ctypes.wintypes
kernel32 = ctypes.WinDLL('kernel32')

from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'windrives')

def get_all_volumes():
    '''
    Return a list of volume paths like \\?\Volume{GUID}\ for all volumes,
    whether they are mounted or not.

    Note: This will include recovery / EFI partitions, which may not be what
    you're looking for. Also see get_drive_letters and get_drive_mounts.

    Thank you Duncan.
    https://stackoverflow.com/a/3075879

    Thank you Mark Tolonen.
    https://stackoverflow.com/a/66976493
    '''
    type_unicode = ctypes.wintypes.LPCWSTR
    type_dword = ctypes.wintypes.DWORD
    type_handle = ctypes.wintypes.HANDLE

    kernel32.FindFirstVolumeW.argtypes = (type_unicode, type_dword)
    kernel32.FindFirstVolumeW.restype = type_handle

    kernel32.FindNextVolumeW.argtypes = (type_handle, type_unicode, type_dword)
    kernel32.FindNextVolumeW.restype = type_handle

    kernel32.FindVolumeClose.argtypes = (type_handle,)
    kernel32.FindVolumeClose.restype = type_handle

    buffer = ctypes.create_unicode_buffer(1024)
    buffer_size = ctypes.sizeof(buffer)

    handle = kernel32.FindFirstVolumeW(buffer, buffer_size)

    volumes = []
    if handle:
        volumes.append(buffer.value)
        while kernel32.FindNextVolumeW(handle, buffer, buffer_size):
            volumes.append(buffer.value)
        kernel32.FindVolumeClose(handle)
    return volumes

def get_drive_info(path):
    '''
    Given a drive path as either:
    - a letter like C or C:\, or
    - a mount path, or
    - a volume path like \\?\Volume{GUID},
    return a dictionary containing its attributes.

    Thanks Nicholas Orlowski
    http://stackoverflow.com/a/12056414
    '''
    letter_match = re.match(r'^([A-Z])(|:|:\\)$', path)
    if letter_match:
        letter = letter_match.group(1)
        path = f'{letter}:\\'

    if path.startswith('\\\\?\\Volume{'):
        mount = get_volume_mount(path)
    else:
        mount = path

    name_buffer = ctypes.create_unicode_buffer(1024)
    filesystem_buffer = ctypes.create_unicode_buffer(1024)
    serial_number = None
    max_component_length = None
    file_system_flags = None

    drive_active = kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(path),
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
        'mount': mount,
    }
    return info

def get_drive_letters():
    '''
    Return a list of all connected drive letters as single-character strings.

    Drives which are mounted to paths instead of letters will not be returned.
    Use get_drive_mounts instead.

    Thanks RichieHindle
    http://stackoverflow.com/a/827398
    '''
    # "If the function succeeds, the return value is a bitmask representing the
    # currently available disk drives. Bit position 0 (the least-significant
    # bit) is drive A, bit position 1 is drive B, bit position 2 is drive C,
    # and so on."
    # https://docs.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlogicaldrives
    letters = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            letters.append(letter)
        bitmask >>= 1
    return letters

def get_drive_map():
    '''
    Return a dict of {mount: info} for all connected drives, where mount is
    either a drive letter or mount path, and info is the dict returned
    by get_drive_info.
    '''
    drives = {mount: get_drive_info(mount) for mount in get_drive_mounts()}
    return drives

def get_drive_mounts():
    '''
    Return a list of all connected drives as either:
    - a letter like C:\ if the volume has a letter, or
    - a mount path if the volume does not have a letter.
    '''
    mounts = []
    for volume in get_all_volumes():
        mount = get_volume_mount(volume)
        if mount:
            mounts.append(mount)
    return mounts

def get_drive_mount_by_name(name):
    '''
    Given the name of a drive (the user-customizable name seen in Explorer),
    return the letter or mount path of that drive.

    Raises KeyError if it is not found.
    '''
    drives = get_drive_map()
    for (mount, info) in drives.items():
        if info['name'] == name:
            return mount
    raise KeyError(name)

def get_volume_mount(volume):
    '''
    Given a volume path like \\?\Volume{GUID}\, return either:
    - a letter like C:\ if the volume has a letter, or
    - a mount path if the volume does not have a letter, or
    - emptystring if the volume is not mounted at all.

    Thank you Duncan.
    https://stackoverflow.com/a/3075879

    Note: The API function is named "GetVolumePathNames..." in the plural,
    and Duncan's original answer uses .split('\0'), but in my testing the
    drives always contain only a single name.
    If the drive has a letter and mount path, only the letter is returned.
    If it has two mount paths, only the first one is returned.
    So, I'll just use a single return value until further notice.
    '''
    buffer = ctypes.create_unicode_buffer(1024)
    length = ctypes.c_int32()
    kernel32.GetVolumePathNamesForVolumeNameW(
        ctypes.c_wchar_p(volume),
        buffer,
        ctypes.sizeof(buffer),
        ctypes.pointer(length),
    )
    return buffer.value
