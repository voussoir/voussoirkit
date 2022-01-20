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
    def __init__(
            self,
            allowance,
            *,
            mode='sleep',
            operation_cost=1,
            period=1,
            starting_balance=None,
        ):
        '''
        allowance:
            Our spending balance per `period` seconds.

        mode:
            'sleep':
                If we do not have the balance for an operation, sleep until we
                do. Then return True every time.

            'reject':
                If we do not have the balance for an operation, do nothing and
                return False. Otherwise subtract the cost and return True.

        operation_cost:
            The default amount to remove from our balance after each operation.
            Pass a `cost` parameter to `self.limit` to use a nondefault value.

        period:
            The number of seconds over which we can perform `allowance`
            operations.

        starting_balance:
            With a value of None, the limiter will be given a starting balance
            of `operation_cost` so that you can perform a single operation as
            soon as you instantiate the object. You can provide another starting
            balance here.

        Although (allowance=1, period=1) and (allowance=30, period=30) can both
        be described as "once per second", the latter allows for much greater
        burstiness of operation. You could spend the whole allowance in a
        single second, then relax for 29 seconds, for example.
        '''
        def positive(x, name):
            if not isinstance(x, (int, float)):
                raise TypeError(f'{name} should be int or float, not {type(x)}.')

            if x <= 0:
                raise ValueError(f'{name} should be > 0, not {x}.')

            return x

        if mode not in ('sleep', 'reject'):
            raise ValueError(f'Invalid mode {repr(mode)}.')

        self.allowance = positive(allowance, 'allowance')
        self.period = positive(period, 'period')
        self.operation_cost = positive(operation_cost, 'operation_cost')
        self.mode = mode

        if starting_balance is None:
            self.balance = operation_cost
        else:
            self.balance = positive(starting_balance, 'starting_balance')

        self.lock = threading.Lock()
        self.last_operation = time.monotonic()

    def __repr__(self):
        return f'{self.__class__.__name__}(allowance={self.allowance}, period={self.period})'

    @property
    def gain_rate(self):
        return self.allowance / self.period

    def _limit(self, cost):
        now = time.monotonic()
        time_diff = now - self.last_operation
        self.balance += time_diff * self.gain_rate
        self.balance = min(self.balance, self.allowance)
        self.last_operation = now

        if self.mode == 'reject' and self.balance < cost:
            success = False
            sleep_needed = 0
            return (success, sleep_needed)

        self.balance -= cost
        success = True

        if self.balance >= 0:
            sleep_needed = 0
        else:
            sleep_needed = abs(self.balance) / self.gain_rate

        return (success, sleep_needed)

    def limit(self, cost=None):
        '''
        See the main class docstring for info about cost and mode behavior.
        '''
        if cost is None:
            cost = self.operation_cost

        with self.lock:
            (success, sleep_needed) = self._limit(cost)

        if sleep_needed > 0:
            time.sleep(sleep_needed)

        return success
