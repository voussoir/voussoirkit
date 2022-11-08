import math
import re
import sys

from voussoirkit import pipeable

def _render_colons(hours, minutes, seconds):
    parts = []
    if hours is not None:
        parts.append(f'{hours:02d}:')
    if minutes is not None:
        parts.append(f'{minutes:02d}:')
    parts.append(f'{seconds:02d}')

    return ''.join(parts)

def _render_letters(hours, minutes, seconds):
    parts = []
    if hours is not None:
        parts.append(f'{hours:02d}h')
    if minutes is not None:
        parts.append(f'{minutes:02d}m')
    parts.append(f'{seconds:02d}s')

    return ''.join(parts)

def hms_to_seconds(hms) -> float:
    '''
    Convert hh:mm:ss string to an integer or float of seconds.
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

def hms_letters_to_seconds(hms) -> float:
    match = re.match(r'(?:(\d+)h)?(?:(\d+)m)?(\d+)s?', hms.strip())
    if not match:
        raise ValueError(f'{hms} does not match 00h00m00s pattern')
    (hours, minutes, seconds) = match.groups()
    seconds = int(seconds)
    if hours:
        seconds += int(hours) * 3600
    if minutes:
        seconds += int(minutes) * 60
    return seconds

def rounds(seconds):
    if seconds > 0 and seconds < 1:
        return 1
    else:
        return round(seconds)

def _seconds_to_hms(
        seconds,
        renderer,
        *,
        force_minutes=False,
        force_hours=False,
    ):
    seconds = rounds(seconds)
    (minutes, seconds) = divmod(seconds, 60)
    (hours, minutes) = divmod(minutes, 60)

    if not (hours or force_hours):
        hours = None

    if not (minutes or hours or force_hours or force_minutes):
        minutes = None

    return renderer(hours, minutes, seconds)

def seconds_to_hms(seconds, **kwargs) -> str:
    '''
    Convert integer number of seconds to an hh:mm:ss string.
    Only the necessary fields are used.
    '''
    return _seconds_to_hms(seconds, renderer=_render_colons, **kwargs)

def seconds_to_hms_letters(seconds, **kwargs) -> str:
    return _seconds_to_hms(seconds, renderer=_render_letters, **kwargs)

def main(args):
    lines = pipeable.input_many(args, strip=True, skip_blank=True)
    for line in lines:
        if ':' in line:
            line = hms_to_seconds(line)
        elif 's' in line:
            line = hms_letters_to_seconds(line)
        else:
            line = float(line)
            if line > 60:
                line = seconds_to_hms(line)

        pipeable.stdout(line)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
