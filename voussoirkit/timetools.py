import datetime

def now():
    return datetime.datetime.now(tz=datetime.timezone.utc)

def now_local():
    return datetime.datetime.now().astimezone()
