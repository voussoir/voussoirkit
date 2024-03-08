import collections
import time

from voussoirkit import sentinel

NO_ITEM = sentinel.Sentinel('no item')

class Cache:
    def __init__(self, maxlen, expiry=float('inf')):
        self.maxlen = maxlen
        self.expiry = expiry
        self.cache = collections.OrderedDict()

        # To prevent excessive purge loops during repeated setitem, only allow
        # a purge once every this many seconds.
        self.max_purge_frequency = 0.5

        self._last_purge = 0

    def __contains__(self, key):
        return self.get(key, fallback=NO_ITEM) is not NO_ITEM

    def __getitem__(self, key):
        '''
        Return the key's value, or raise KeyError.
        '''
        # Let KeyError raise to caller.
        (value, timestamp) = self.cache.pop(key)

        now = time.time()
        if (now - timestamp) > self.expiry:
            raise KeyError(key)

        self.cache[key] = (value, timestamp)
        return value

    def __len__(self):
        '''
        Purge expired items, then count the length.
        Due to the purge, this method is not O(1) as most len methods are.
        '''
        self._purge_expired()
        return len(self.cache)

    def __setitem__(self, key, value):
        # If the key was already present, we don't need to worry about maxlen
        # because the net change is zero. If it was not present (KeyError) we
        # check the maxlen and pop the oldest item if needed.
        # Either way we update the timestamp.
        try:
            self.cache.pop(key)
        except KeyError:
            if len(self) >= self.maxlen:
                self.cache.popitem(last=False)
        self.cache[key] = (value, time.time())

    def _purge_expired(self):
        now = time.time()
        if now - self._last_purge < self.max_purge_frequency:
            return

        for (key, (value, timestamp)) in list(self.cache.items()):
            if (now - timestamp) > self.expiry:
                self.cache.pop(key)

        self._last_purge = now

    def clear(self):
        '''
        Remove everything from the cache.
        '''
        self.cache.clear()

    def get(self, key, fallback=None):
        '''
        Return the key's value, or fallback in case of KeyError.
        '''
        try:
            return self[key]
        except KeyError:
            return fallback

    def keys(self):
        return list(self.cache.keys())

    def items(self):
        return [(key, value) for (key, (value, timestamp)) in self.cache.items()]

    def values(self):
        return [value for (value, timestamp) in self.cache.values()]

    def pop(self, key):
        '''
        Remove the key and return its value, or raise KeyError.
        '''
        (value, timestamp) = self.cache.pop(key)
        return value

    def remove(self, key):
        '''
        Remove the item and ignore KeyError.
        '''
        try:
            self.pop(key)
        except KeyError:
            pass
