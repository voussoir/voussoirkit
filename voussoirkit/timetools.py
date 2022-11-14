import datetime

def now():
    return datetime.datetime.now(tz=datetime.timezone.utc)

def now_local():
    return datetime.datetime.now().astimezone()

def fromtimestamp(unix):
    return datetime.datetime.utcfromtimestamp(unix).replace(tzinfo=datetime.timezone.utc)

def fromtimestamp_local(unix):
    return datetime.datetime.fromtimestamp(unix).astimezone()
