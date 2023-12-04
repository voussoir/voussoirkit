'''
Find time, filesize, or bitrate, given two of the three.

For example:

kbps.py --time 1:00:00 --size 2g
kbps.py --time 1:00:00 --kbps 4660
kbps.py --size 2g --kpbps 4660
'''
import argparse
import sys

from voussoirkit import bytestring
from voussoirkit import hms

def kbps(time=None, size=None, kbps=None):
    if [time, size, kbps].count(None) != 1:
        raise ValueError('Incorrect number of unknowns.')

    if time is None:
        kilobits = size / 128
        time = kilobits / kbps

    if size is None:
        kibs = kbps / 8
        size = kibs * 1024
        size *= time

    if kbps is None:
        kibs = size / 1024
        kilobits = kibs * 8
        kbps = kilobits / time

    return (time, size, kbps)

def kbps_argparse(args):
    time = args.time and hms.hms_to_seconds(args.time)
    size = args.size and bytestring.parsebytes(args.size)
    kibs = args.kbps and int(args.kbps)

    (time, size, kibs) = kbps(time=time, size=size, kbps=kibs)

    print(f'{hms.seconds_to_hms_letters(time)} @ {round(kibs, 4)} kbps = {bytestring.bytestring(size)}')

def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('-t', '--time', dest='time', default=None)
    parser.add_argument('-s', '--size', dest='size', default=None)
    parser.add_argument('-k', '--kbps', dest='kbps', default=None)
    parser.set_defaults(func=kbps_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
