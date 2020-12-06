'''
Create the file, or update the last modified timestamp.
'''
import argparse
import os
import sys

from voussoirkit import pipeable
from voussoirkit import winglob

def touch_argparse(args):
    patterns = [pattern for arg in args.patterns for pattern in pipeable.input(arg)]
    for pattern in patterns:
        filenames = winglob.glob(pattern)

        if len(filenames) == 0 and not winglob.is_glob(pattern):
            open(pattern, 'a').close()
            print(pattern)

        for filename in filenames:
            os.utime(filename)
            print(filename)

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('patterns', nargs='+')
    parser.set_defaults(func=touch_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
