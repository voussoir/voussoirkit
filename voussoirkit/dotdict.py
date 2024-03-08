'''
Overall, I like types.SimpleNamespace. But I decided to make dotdict because:
1. SimpleNamespace is a cumbersome name to type and to look at.
2. I wanted my class to support default values.
'''
from voussoirkit import sentinel

NO_DEFAULT = sentinel.Sentinel('NO_DEFAULT')

class DotDict:
    def __init__(self, __dict=None, *, default=NO_DEFAULT, **kwargs):
        self.__default = default
        if __dict:
            self.__dict__.update(__dict)
        self.__dict__.update(**kwargs)

    def __delattr__(self, key):
        self.__dict__.pop(key, None)

    def __getattr__(self, key):
        try:
            return self.__dict__[key]
        except KeyError as exc:
            if self.__default is not NO_DEFAULT:
                return self.__default
            raise AttributeError from exc

    def __setattr__(self, key, value):
        self.__dict__[key] = value

    def _to_dict(self):
        display = self.__dict__.copy()
        display.pop('_DotDict__default')
        return display

    def __iter__(self):
        return iter(self._to_dict().items())

    def __repr__(self):
        display = self.__dict__.copy()
        display.pop('_DotDict__default')
        return f'DotDict({display})'
