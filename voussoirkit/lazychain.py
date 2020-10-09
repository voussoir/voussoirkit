import collections

class LazyChain:
    '''
    You may be familiar with itertools.chain, which chains two iterables into
    one. However, I wanted a data structure where I could add more and more
    generators into the chain without repeatedly calling
    `chain = itertools.chain(chain, more)`.
    '''
    def __init__(self):
        self.iters = collections.deque()

    def __iter__(self):
        return self

    def __next__(self):
        while self.iters:
            try:
                return next(self.iters[0])
            except StopIteration:
                self.iters.popleft()
        raise StopIteration()

    def append(self, item):
        '''
        Add a single item to the chain.
        '''
        self.iters.append(iter((item,)))

    def extend(self, sequence):
        '''
        Add the contents of a list, tuple, generator... to the chain.
        Make sure not to exhaust the generator outside of this chain!
        '''
        self.iters.append(iter(sequence))
