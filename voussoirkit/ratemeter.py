import collections
import threading
import time

class RateMeter:
    def __init__(self, span):
        '''
        This class is used to calculate a rolling average of
        units per second over `span` seconds.

        Set `span` to None to calculate unit/s over the lifetime of the object
        after the first digest, rather than over a span. This saves the effort
        of tracking timestamps; so don't just use a large number!
        '''
        self.sum = 0
        self.span = span

        self.lock = threading.Lock()
        self.tracking = collections.deque()
        self.first_digest = None

    def _digest(self, value):
        now = time.monotonic()
        self.sum += value

        if self.span is None:
            if self.first_digest is None:
                self.first_digest = now
            return

        expire_cutoff = now - self.span
        while len(self.tracking) > 0 and self.tracking[0][0] < expire_cutoff:
            (timestamp, pop_value) = self.tracking.popleft()
            self.sum -= pop_value

        if len(self.tracking) == 0 or self.tracking[-1] != now:
            self.tracking.append([now, value])
        else:
            self.tracking[-1][1] += value

    def digest(self, value):
        with self.lock:
            return self._digest(value)

    def _report(self):
        # Flush the old values, ensure self.first_digest exists.
        self._digest(0)

        if self.span is None:
            now = time.monotonic()
            time_interval = now - self.first_digest
        else:
            # No risk of IndexError because the digest(0) ensures we have
            # at least one entry.
            time_interval = self.tracking[-1][0] - self.tracking[0][0]

        if time_interval == 0:
            return (self.sum, 0, self.sum)

        rate = self.sum / time_interval
        return (self.sum, time_interval, rate)

    def report(self):
        '''
        Return a tuple containing the running sum, the time span over which the
        rate has been calculated, and the rate in units per second.

        (sum, time_interval, rate)
        '''
        with self.lock:
            return self._report()
