import datetime
import re
import time

EPOCH = datetime.datetime(
    year=1993,
    month=9,
    day=1,
)

def strftime(format, tpl=None):
    now = datetime.datetime.now()
    diff = now - EPOCH

    day = str(diff.days + 1)
    day_of_year = str(244 + diff.days)

    changes = {
        r'%b': 'Sep',
        r'%B': 'September',
        r'%d': day,
        r'%-d': day,
        r'%j': day_of_year,
        r'%-j': day_of_year,
        r'%m': '09',
        r'%-m': '9',
        r'%Y': '1993',
        r'%y': '93',
    }
    for (key, value) in changes.items():
        key = r'(?<!%)' + key
        format = re.sub(key, value, format)

    if tpl is not None:
        return time.strftime(format, tpl)
    else:
        return time.strftime(format)

if __name__ == '__main__':
    print(strftime('%Y-%m-%d %H:%M:%S'))
