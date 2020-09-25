'''
This function is slow and ugly, but I need a way to safely print unicode strings
on systems that don't support it without crippling those who do.
'''
import sys

def safeprint_handle(text, *, file_handle, end='\n'):
    for character in text:
        try:
            file_handle.write(character)
        except UnicodeError:
            file_handle.write('?')
    file_handle.write(end)

def safeprint_stdout(text, *, end='\n'):
    safeprint_handle(text=text, file_handle=sys.stdout, end=end)
    sys.stdout.flush()

def safeprint(text, *, file_handle=None, end='\n'):
    if file_handle is not None:
        return safeprint_handle(text=text, file_handle=file_handle, end=end)
    else:
        return safeprint_stdout(text=text, end=end)
