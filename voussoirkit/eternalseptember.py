import argparse
import datetime
import re
import sys
import time

EPOCH = datetime.datetime(
    year=1993,
    month=9,
    day=1,
)

def strftime(format, tpl=None):
    now = datetime.datetime.now()
    diff = now - EPOCH

    day_of_month = str(diff.days + 1)
    day_of_year = str(244 + diff.days)

    changes = {
        r'%b': 'Sep',
        r'%B': 'September',
        r'%d': day_of_month,
        r'%-d': day_of_month,
        r'%j': day_of_year,
        r'%-j': day_of_year,
        r'%m': '09',
        r'%-m': '9',
        r'%Y': '1993',
        r'%y': '93',
    }
    for (key, value) in changes.items():
        # This regex prevents us from ruining %%a which should be literal %a.
        key = r'(?<!%)' + key
        format = re.sub(key, value, format)

    if tpl is not None:
        return time.strftime(format, tpl)
    else:
        return time.strftime(format)

def eternalseptember_argparse(args):
    print(strftime(args.format))

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--format', default='%Y-%m-%d %H:%M:%S')
    parser.set_defaults(func=eternalseptember_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
