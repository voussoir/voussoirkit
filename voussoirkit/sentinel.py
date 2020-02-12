class Sentinel:
    '''
    Sentinel objects are used when you need to have some kind of default,
    placeholder, or special value that can't be confused with any other value
    in your program. For example, if you are waiting for a function to return a
    value, but you use `None` as a placeholder, someone might get confused and
    think that the function actually returned None.

    You can get cheap sentinels by just creating plain Python `object()`s, but
    they are bad for printing because you'll just see an ID and not know what
    the sentinel represents. This simple Sentinel class lets you give them a
    name and adjust their truthyness which can be useful.

    Some implementations of sentinels also make them singletons. These ones are
    not singletons! Separate sentinels will never == each other even if you use
    the same name!
    '''
    def __init__(self, name, truthyness=True):
        self.name = name
        self.truthyness = truthyness

    def __bool__(self):
        return bool(self.truthyness)

    def __repr__(self):
        return f'<Sentinel {repr(self.name)} id={id(self)} like {bool(self.truthyness)}>'
