from voussoirkit import sentinel

NO_DEFAULT = sentinel.Sentinel('NO_DEFAULT')

class DotDict:
    def __init__(self, default=NO_DEFAULT, **kwargs):
        self.__default = default
        self.__dict__.update(**kwargs)

    def __getattr__(self, key):
        try:
            return self.__dict__[key]
        except KeyError:
            if self.__default is not NO_DEFAULT:
                return self.__default
            raise

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def __repr__(self):
        return f'DotDict {self.__dict__}'
