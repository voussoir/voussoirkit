import datetime

EPOCH = datetime.datetime(
    year=1993,
    month=9,
    day=1,
    tzinfo=datetime.timezone.utc,
)

def normalize_date(date):
    if isinstance(date, datetime.datetime):
        pass
    elif isinstance(date, (int, float)):
        date = datetime.datetime.utcfromtimestamp(date)
        date = date.replace(tzinfo=datetime.timezone.utc)
    else:
        raise TypeError('Unrecognized date type.')

    return date

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def september_day(date):
    '''
    Return the ES day of the month for this date.
    '''
    date = normalize_date(date)
    diff = date - EPOCH
    days = diff.days + 1
    return days

def september_now(strf):
    return september_string(now(), strf)

def september_string(date, strf):
    '''
    Return the ES formatted string for this date.
    '''
    date = normalize_date(date)
    day = str(september_day(date))

    strf = strf.replace('%a', date.strftime('%a'))
    strf = strf.replace('%A', date.strftime('%A'))
    strf = strf.replace('%d', day)
    strf = strf.replace('%-d', day)

    date = date.replace(month=EPOCH.month, year=EPOCH.year)
    return date.strftime(strf)

if __name__ == '__main__':
    print(september_now('%Y %B %d %H:%M:%S'))
