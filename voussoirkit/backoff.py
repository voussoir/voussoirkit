'''
The Backoff classes are intended to be used to control `time.sleep` with
varying backoff strategies.

Example:

bo = backoff.Linear(m=1, b=1, max=30)
while True:
    try:
        something()
    except Exception:
        time.sleep(bo.next())
    else:
        bo.reset()

If you want to add random fuzziness to your sleeps, that should be done on the
calling end. For example, `bo.next() + (random.random() - 0.5)`.
'''
class Backoff:
    def __init__(self, max):
        self.x = 0
        if max is None:
            pass
        elif max <= 0:
            raise ValueError(f'max must be positive, not {max}.')
        self.max = max

    def current(self) -> float:
        '''
        Return the current backoff value without advancing.
        '''
        y = self._calc()
        if self.max is not None:
            y = min(y, self.max)
        return y

    def next(self) -> float:
        '''
        Return the current backoff value, then advance x.
        '''
        y = self.current()
        self.x += 1
        return y

    def reset(self) -> None:
        '''
        Reset x to 0.
        '''
        self.x = 0

    def rewind(self, steps) -> None:
        '''
        Subtract this many steps from x, to ease up the backoff without
        entirely resetting.
        '''
        self.x = max(0, self.x - steps)

####################################################################################################

class Exponential(Backoff):
    '''
    Exponential backoff produces next = (a**x) + b.
    '''
    def __init__(self, a, b, *, max):
        super().__init__(max)
        self.a = a
        self.b = b
        self.max = max

    def _calc(self):
        return (self.a ** self.x) + self.b

class Linear(Backoff):
    '''
    Linear backoff produces next = (m * x) + b.
    '''
    def __init__(self, m, b, *, max):
        super().__init__(max)
        self.m = m
        self.b = b
        self.max = max

    def _calc(self):
        return (self.m * self.x) + self.b

class Quadratic(Backoff):
    '''
    Quadratic backoff produces next = (a * x**2) + (b * x) + c.
    '''
    def __init__(self, a, b, c, *, max):
        super().__init__(max)
        self.a = a
        self.b = b
        self.c = c
        self.max = max

    def _calc(self):
        return (self.a * self.x**2) + (self.b * self.x) + self.c

'''
people are backing off
you'll get used to it
'''
