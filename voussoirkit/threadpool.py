'''
The documentation for the classes and methods are below. Here are some examples
of threadpool in use:

1. Powering a single api scraping generator with many threads:

pool = threadpool.ThreadPool(thread_count, paused=True)
job_gen = ({'function': api.get_item, 'kwargs': {'id': i}} for i in range(lower, upper+1))
pool.add_generator(job_gen)
for job in pool.result_generator():
    if job.exception:
        raise job.exception
    if job.value is not None:
        yield job.value

'''
import collections
import queue
import threading

from voussoirkit import lazychain
from voussoirkit import sentinel

PENDING = sentinel.Sentinel('PENDING')
RUNNING = sentinel.Sentinel('RUNNING')
FINISHED = sentinel.Sentinel('FINISHED')
RAISED = sentinel.Sentinel('RAISED')

NO_RETURN = sentinel.Sentinel('NO_RETURN', truthyness=False)
NO_EXCEPTION = sentinel.Sentinel('NO_EXCEPTION', truthyness=False)

class ThreadPoolException(Exception):
    pass

class PoolClosed(ThreadPoolException):
    pass

class ThreadPool:
    '''
    The ThreadPool is used to perform large numbers of tasks using a pool of
    worker threads. Jobs are run in the order they are added.

    The pool supports two main paradigms of usage:

    1. Callback / async style
        If the job function performs your desired side effects by itself, or is
        given a callback function, you can simply add it to the pool and wait
        for it to run.

    2. Generator style
        If you want to yield the job results back to the main thread for
        processing (e.g. you are feeding the results into sqlite, which must be
        done on the thread which opened the sqlite connection), you can use
        `result_generator` to get each job in the order they were added to the
        pool. This style also makes it easier to terminate the main thread when
        a single job encounters an issue. Just `raise job.exception`.
    '''
    def __init__(self, size, paused=True):
        '''
        size:
            The number of worker threads.

        paused:
            If True, the pool will start in a paused state and you will have to
            call `start` to start it. If False, the pool will run as soon as
            jobs are added to it.
        '''
        if not isinstance(size, int):
            raise TypeError(f'size must be an int, not {type(size)}.')
        if size < 1:
            raise ValueError(f'size must be >= 1, not {size}.')

        self.max_size = size
        self.paused = paused

        self._closed = False
        self._running_count = 0
        self._result_queue = None
        self._pending_jobs = lazychain.LazyChain()
        self._job_manager_lock = threading.Lock()
        self._all_done_event = threading.Event()
        self._all_done_event.set()

    def _job_finished(self):
        '''
        When a job finishes, it will call here so that a new job can be started.
        '''
        self._running_count -= 1

        if not self.paused:
            self.start()

    @property
    def closed(self):
        return self.closed

    @property
    def running_count(self):
        return self._running_count

    def assert_not_closed(self):
        '''
        If the pool is closed (because you called `join`), raise PoolClosed.
        Otherwise do nothing.
        '''
        if self._closed:
            raise PoolClosed()

    def add(self, function, *, name=None, callback=None, args=tuple(), kwargs=dict()):
        '''
        Add a new job to the pool.

        See the Job class for parameter details.
        '''
        self.assert_not_closed()

        job = Job(
            pool=self,
            function=function,
            name=name,
            args=args,
            kwargs=kwargs,
        )
        self._pending_jobs.append(job)

        if not self.paused:
            self.start()

        return job

    def add_generator(self, kwargs_gen):
        '''
        Add jobs from a generator which yields kwarg dictionaries. Unlike
        `add` and `add_many`, the Job objects are not returned by this method
        (since they don't exist yet!). If you want them, use `result_generator`
        to iterate the pool's jobs as they complete. Otherwise, they should
        have their own side effects or use a callback.

        See the Job class for kwarg details.
        '''
        self.assert_not_closed()

        these_jobs = (Job(pool=self, **kwargs) for kwargs in kwargs_gen)
        self._pending_jobs.extend(these_jobs)

        if not self.paused:
            self.start()

    def add_many(self, kwargss):
        '''
        Add multiple new jobs to the pool at once. This is better than calling
        `add` in a loop because we only have to aquire the lock one time.

        Provide an iterable of kwarg dictionaries. That is:
        [
            {'function': print, 'args': [4], 'name': '4'},
            {'function': sample, 'kwargs': {'x': 2}},
        ]

        See the Job class for kwarg details.
        '''
        self.assert_not_closed()

        these_jobs = [Job(pool=self, **kwargs) for kwargs in kwargss]
        self._pending_jobs.extend(these_jobs)

        if not self.paused:
            self.start()

        return these_jobs

    def join(self):
        '''
        Permanently close the pool, preventing any new jobs from being added,
        and block until all jobs are complete.
        '''
        self._closed = True
        self.start()
        self._all_done_event.wait()

    def result_generator(self):
        '''
        This generator will start the job pool, then yield finished/raised Job
        objects in the order they were added. Note that a slow job will
        therefore hold up the generator, though it will not stop the job pool
        from running and spawning new jobs in their other threads.

        For best results, you should create the pool in the paused state, add
        your jobs, then use this method to start the pool. Any jobs that run
        while the result_generator is not active will not be stored, since we
        don't necessarily know if this method will ever be used. So, any jobs
        that start before the result_generator is active will not be yielded
        and will simply be lost to garbage collection.

        If more jobs are added while the generator is running, they will be
        yielded as expected.

        When there are no more outstanding jobs, the generator will stop
        iteration and return. If the pool was paused before generating, it
        will be paused again.
        '''
        if self._result_queue is not None:
            raise TypeError('The result generator is already open.')
        self._result_queue = queue.Queue()

        was_paused = self.paused
        self.start()
        while (not self._all_done_event.is_set()) or (not self._result_queue.empty()):
            job = self._result_queue.get()
            job.join()
            yield job
            self._result_queue.task_done()
        self._result_queue = None
        if was_paused:
            self.paused = True

    def start(self):
        self.paused = False
        with self._job_manager_lock:
            available = self.max_size - self._running_count

            no_more_jobs = False
            for x in range(available):
                try:
                    job = next(self._pending_jobs)
                except StopIteration:
                    no_more_jobs = True
                    break

                self._all_done_event.clear()
                job.start()
                self._running_count += 1
                if self._result_queue is not None:
                    self._result_queue.put(job)

            if self._running_count == 0 and no_more_jobs:
                self._all_done_event.set()

class Job:
    '''
    Each job contains one function that it will call when it is started.

    If the function completes successfully you will find the return value in
    `job.value`. If it raises an exception, you'll find it in `job.exception`,
    although the thread itself will not raise.

    All job threads are daemons and will not prevent the main thread from
    terminating. Call `job.join()` or `pool.join()` in the main thread to
    ensure jobs complete.
    '''
    def __init__(self, pool, function, *, name=None, callback=None, args=tuple(), kwargs=dict()):
        '''
        When this job is started, `function(*args, **kwargs)` will be called.

        name:
            An optional value that will appear in the repr of the job and
            has no other purpose. Use this if you intend to print(job) and want
            a human friendly name string.

        callback:
            An optional function which will be called as `callback(job)` after
            the job is finished running. Use this for async-style processing of
            the job. Note that the callback is called via the job's thread, so
            make sure it is memory safe.
        '''
        self.pool = pool
        self.name = name
        self.status = PENDING
        self.function = function
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.value = NO_RETURN
        self.exception = NO_EXCEPTION
        self._thread = None

        # _joinme_lock works because it is possible for a single thread to block
        # itself by calling `lock.acquire()` twice. The first call is here,
        # and the second call is in `join` so that join will block until the
        # lock is released by the job's finishing phase.
        self._joinme_lock = threading.Lock()
        self._joinme_lock.acquire()

    def __repr__(self):
        if self.name:
            return f'<{self.status.name} Job {repr(self.name)}>'
        else:
            return f'<{self.status.name} Job on {self.function}>'

    def _run(self):
        try:
            self.value = self.function(*self.args, **self.kwargs)
            self.status = FINISHED
        except BaseException as exc:
            self.exception = exc
            self.status = RAISED
        self._thread = None
        self._joinme_lock.release()
        self.pool._job_finished()
        if self.callback is not None:
            self.callback(self)

    def join(self):
        '''
        Block until this job runs and completes.
        '''
        self._joinme_lock.acquire()
        self._joinme_lock.release()

    def start(self):
        self.status = RUNNING
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
