'''
Instead of adding every program's directory to my system PATH, I prefer having
a single directory on my PATH which contains Windows shortcuts (lnk files)
pointing to each program.
Windows lnks are different from softlinks because they maintain the program's
real directory necessary for loading nearby dlls etc.
However, this breaks `shutil.which` --> `subprocess.run` because subprocess.run
with shell=False does not interpret lnks, and needs a direct path to the exe.

So, this module provides a function `which` that if it finds an lnk file, will
return the exe path, otherwise behaves the same as normal shutil which.
'''
import os
import shutil
try:
    import winshell
    # This fixes some "CoInitialize has not been called" errors which I found
    # were occuring intermittently on some subprocess calls.
    winshell.pythoncom.CoInitialize()
except ImportError:
    winshell = None

def which(cmd, *args, **kwargs):
    path = shutil.which(cmd, *args, **kwargs)

    if path is None:
        return None

    if os.name == 'nt' and winshell and path.lower().endswith('.lnk'):
        path = winshell.Shortcut(path).path

    return path
