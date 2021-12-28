class MutableBase:
    def __init__(self, value):
        self.set(value)

    def __repr__(self):
        return f'{self.__module__}.{self.__class__.__name__}({repr(self._value)})'

    @property
    def value(self):
        return self._value

    def get(self):
        return self._value

    def set(self, value):
        if type(value) not in self._types:
            raise TypeError(value)

        self._value = value

class Boolean(MutableBase):
    _types = [bool]

    def __bool__(self):
        return self._value

class Bytes(MutableBase):
    _types = [bytes]

class Float(MutableBase):
    _types = [int, float]

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)

class Integer(MutableBase):
    _types = [int]

    def __int__(self):
        return int(self._value)

    def __float__(self):
        return float(self._value)

class String(MutableBase):
    _types = [str]

    def __str__(self):
        return self._value
