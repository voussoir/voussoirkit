class Boolean:
    def __init__(self, value):
        self.set(value)

    def __bool__(self):
        return self.__value

    def get(self):
        return self.__value

    def set(self, value):
        if type(value) is not bool:
            raise TypeError(value)

        self.__value = value

class Bytes:
    def __init__(self, value):
        self.set(value)

    def get(self):
        return self.__value

    def set(self, value):
        if type(value) is not bytes:
            raise TypeError(value)

        self.__value = value

class Float:
    def __init__(self, value):
        self.set(value)

    def get(self):
        return self.__value

    def set(self, value):
        if type(value) not in (int, float):
            raise TypeError(value)

        self.__value = value

class Integer:
    def __init__(self, value):
        self.set(value)

    def get(self):
        return self.__value

    def set(self, value):
        if type(value) is not int:
            raise TypeError(value)

        self.__value = value

class String:
    def __init__(self, value):
        self.set(value)

    def __str__(self):
        return self.__value

    def get(self):
        return self.__value

    def set(self, value):
        if type(value) is not str:
            raise TypeError(value)

        self.__value = value
