import threading
import time

class Ratelimiter:
    '''
    The Ratelimiter class is used to limit how often you perform some other
    action. Just create a Ratelimiter object with the allowance you need, then
    call `limit()` before doing the thing you wish to ratelimit.

    Example:

        download_limiter = Ratelimiter(allowance=1, period=3)

        for file_url in file_urls:
            download_limiter.limit()
            download(file_url)
    '''
    def __init__(self, allowance, period=1, operation_cost=1, mode='sleep'):
        '''
        allowance:
            Our spending balance per `period` seconds.

        period:
            The number of seconds over which we can perform `allowance` operations.

        operation_cost:
            The default amount to remove from our balance after each operation.
            Pass a `cost` parameter to `self.limit` to use a nondefault value.

        mode:
            'sleep':
                If we do not have the balance for an operation, sleep until we
                do. Then return True every time.

            'reject':
                If we do not have the balance for an operation, do nothing and
                return False. Otherwise subtract the cost and return True.

        Although (allowance=1, period=1) and (allowance=30, period=30) can both
        be described as "once per second", the latter allows for much greater
        burstiness of operation. You could spend the whole allowance in a
        single second, then relax for 29 seconds, for example.
        '''
        if mode not in ('sleep', 'reject'):
            raise ValueError(f'Invalid mode {repr(mode)}.')

        self.allowance = allowance
        self.period = period
        self.operation_cost = operation_cost
        self.mode = mode
        self.lock = threading.Lock()

        self.last_operation = time.monotonic()
        self.balance = 0

    @property
    def gain_rate(self):
        return self.allowance / self.period

    def _limit(self, cost):
        now = time.monotonic()
        time_diff = now - self.last_operation
        self.balance += time_diff * self.gain_rate
        self.balance = min(self.balance, self.allowance)

        if self.balance >= cost:
            self.balance -= cost
            successful = True

        elif self.mode == 'reject':
            successful = False

        else:
            deficit = cost - self.balance
            time_needed = deficit / self.gain_rate
            time.sleep(time_needed)
            self.balance = 0
            successful = True

        self.last_operation = now
        return successful

    def limit(self, cost=None):
        '''
        See the main class docstring for info about cost and mode behavior.
        '''
        if cost is None:
            cost = self.operation_cost

        with self.lock:
            return self._limit(cost)
