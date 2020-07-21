import math
import sys

def hms_to_seconds(hms):
    '''
    Convert hh:mm:ss string to an integer seconds.
    '''
    parts = hms.split(':')
    seconds = 0
    if len(parts) > 3:
        raise ValueError(f'{hms} doesn\'t match the HH:MM:SS format.')
    if len(parts) == 3:
        seconds += int(parts[0]) * 3600
        parts.pop(0)
    if len(parts) == 2:
        seconds += int(parts[0]) * 60
        parts.pop(0)
    if len(parts) == 1:
        seconds += float(parts[0])
    return seconds

def seconds_to_hms(seconds):
    '''
    Convert integer number of seconds to an hh:mm:ss string.
    Only the necessary fields are used.
    '''
    seconds = math.ceil(seconds)
    (minutes, seconds) = divmod(seconds, 60)
    (hours, minutes) = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(hours)
    if hours or minutes:
        parts.append(minutes)
    parts.append(seconds)
    hms = ':'.join(f'{part:02d}' for part in parts)
    return hms

def main(args):
    from voussoirkit import pipeable
    for line in pipeable.go(args, strip=True, skip_blank=True):
        if ':' in line:
            line = hms_to_seconds(line)
        else:
            line = float(line)
            if line > 60:
                line = seconds_to_hms(line)

        pipeable.output(f'{line}')

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
