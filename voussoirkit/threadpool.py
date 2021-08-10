'''
The documentation for the classes and methods are below. Here are some examples
of threadpool in use:

1. Powering a single api scraping generator with many threads:

>>> pool = threadpool.ThreadPool(thread_count, paused=True)
>>> job_gen = ({'function': api.get_item, 'kwargs': {'id': i}} for i in range(lower, upper+1))
>>> pool.add_generator(job_gen)
>>> for job in pool.result_generator():
>>>     if job.exception:
>>>         raise job.exception
>>>     if job.value is not None:
>>>         yield job.value

2. Git-fetching a bunch of repositories with no error handling:

>>> def git_fetch(d):
>>>     command = [GIT, '-C', d, 'fetch', '--all']
>>>     print(command)
>>>     subprocess.check_output(command, stderr=subprocess.STDOUT)
>>>
>>> def callback(job):
>>>     if job.exception:
>>>         print(f'{job.name} caused {job.exception}.')
>>>
>>> pool = threadpool.ThreadPool(thread_count, paused=False)
>>> kwargss = [{'function': git_fetch, 'args': [d], 'name': d, 'callback': callback} for d in dirs]
>>> pool.add_many(kwargss)
>>> pool.join()
'''
import logging
import queue
import threading
import traceback

from voussoirkit import lazychain
from voussoirkit import sentinel

log = logging.getLogger('threadpool')

PENDING = sentinel.Sentinel('PENDING')
RUNNING = sentinel.Sentinel('RUNNING')
FINISHED = sentinel.Sentinel('FINISHED')
RAISED = sentinel.Sentinel('RAISED')

NO_MORE_JOBS = sentinel.Sentinel('NO_MORE_JOBS')

NO_RETURN = sentinel.Sentinel('NO_RETURN', truthyness=False)
NO_EXCEPTION = sentinel.Sentinel('NO_EXCEPTION', truthyness=False)

class ThreadPoolException(Exception):
    pass

class PoolClosed(ThreadPoolException):
    pass

class PooledThread:
    def __init__(self, pool):
        self.pool = pool
        self.thread = threading.Thread(target=self.start)
        self.thread.daemon = True
        self.thread.start()

    def __repr__(self):
        return f'PooledThread {self.thread}'

    def _run_once(self):
        # Any exceptions caused by the job's primary function are already
        # wrapped safely, but there are two other sources of potential
        # exceptions:
        # 1. A generator given to add_generator that encounters an exception
        #    while generating the kwargs causes get_next_job to raise.
        # 2. The callback function given to the Job raises.
        # It's hard to say what the correct course of action is, but I
        # realllly don't want them taking down the whole worker thread.
        try:
            job = self.pool.get_next_job()
        except BaseException:
            traceback.print_traceback()
            return

        if job is NO_MORE_JOBS:
            return NO_MORE_JOBS

        log.debug('%s is running job %s.', self, job)
        self.pool._running_count += 1
        try:
            job.run()
        except BaseException:
            traceback.print_traceback()
        self.pool._running_count -= 1

    def join(self):
        log.debug('%s is joining.', self)
        self.thread.join()

    def start(self):
        while True:
            # Let's wait for jobs_available first and unpaused second.
            # If the time between the two waits is very long, the worst thing
            # that can happen is there are no more jobs by the time we get
            # there, and the loop comes around again. On the other hand, if
            # unpaused.wait is first and the time until available.wait is very
            # long, we might wind up running a job despite the user pausing
            # the pool in the interim.
            self.pool._jobs_available.wait()
            self.pool._unpaused_event.wait()
            status = self._run_once()
            if status is NO_MORE_JOBS and self.pool.closed:
                break

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

        self._unpaused_event = threading.Event()
        if not paused:
            self._unpaused_event.set()

        self._jobs_available = threading.Event()

        self._closed = False
        self._running_count = 0
        self._result_queue = None
        self._pending_jobs = lazychain.LazyChain()
        self._job_manager_lock = threading.Lock()

        self._size = size
        self._threads = [PooledThread(pool=self) for x in range(size)]

    @property
    def closed(self):
        return self._closed

    @property
    def paused(self):
        return not self._unpaused_event.is_set()

    @property
    def running_count(self):
        return self._running_count

    @property
    def size(self):
        return self._size

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
        self._jobs_available.set()

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
        self._jobs_available.set()

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

        kwargss = list(kwargss)
        if not kwargss:
            raise ValueError(f'{kwargss} must not be empty.')

        these_jobs = [Job(pool=self, **kwargs) for kwargs in kwargss]
        self._pending_jobs.extend(these_jobs)
        self._jobs_available.set()

        return these_jobs

    def get_next_job(self):
        with self._job_manager_lock:
            try:
                job = next(self._pending_jobs)
            except StopIteration:
                # If we ARE closed, we want to keep the flag set so that all
                # the threads can keep waking up and seeing no more jobs.
                if not self.closed:
                    self._jobs_available.clear()
                if self._result_queue is not None:
                    # If the user provided a generator to add_generator that
                    # actually produces no items, and then immediately starts
                    # waiting inside result_generator for the results, they
                    # will hang as _result_queue never gets anything.
                    # So, here's this.
                    self._result_queue.put(NO_MORE_JOBS)
                return NO_MORE_JOBS
            else:
                if self._result_queue is not None:
                    # This will block if the queue is full.
                    self._result_queue.put(job)
                return job

    def join(self):
        '''
        Permanently close the pool, preventing any new jobs from being added,
        and block until all jobs are complete.
        '''
        log.debug('%s is joining.', self)
        self._closed = True
        # The threads which are currently paused at _jobs_available.wait() need
        # to be woken up so they can realize the pool is closed and break.
        self._jobs_available.set()
        self.start()
        for thread in self._threads:
            thread.join()

    def result_generator(self, *, buffer_size=None):
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
        will be paused again. This prevents subsequently added jobs from being
        lost as described.

        buffer_size:
            The size of the buffer which holds jobs before they are yielded.
            If you expect your production to outpace your consumption, you may
            wish to set this value to prevent high memory usage. When the buffer
            is full, new jobs will be blocked from starting.
        '''
        if self._result_queue is not None:
            raise TypeError('The result generator is already open.')

        self._result_queue = queue.Queue(maxsize=buffer_size or 0)

        was_paused = self.paused

        self.start()
        # Considerations for the while loop condition:
        # Why `jobs_available.is_set`: Consider a group of slow-running threads
        # are launched and the jobs are added to the result_queue. The caller
        # of this generator consumes all of them before the threads finish and
        # start a new job. So, we need to watch jobs_available.is_set to know
        # that even though the result_queue is currently empty, we can expect
        # more to be ready soon and shouldn't break yet.
        # Why `not results_queue.empty`: Consider a group of fast-running
        # threads are launched, and exhaust all available jobs. So, we need to
        # watch that result_queue is not empty and has more results.
        # Why not `not closed`: After the pool is closed, the outstanding jobs
        # still need to finish. Closing does not imply pausing or cancelling
        # jobs.
        while self._jobs_available.is_set() or not self._result_queue.empty():
            job = self._result_queue.get()
            if job is NO_MORE_JOBS:
                self._result_queue.task_done()
                break
            job.join()
            yield job
            self._result_queue.task_done()
        self._result_queue = None

        if was_paused:
            self.pause()

    def pause(self):
        self._unpaused_event.clear()

    def start(self):
        self._unpaused_event.set()

class Job:
    '''
    Each job contains one function that it will call when it is started.

    If the function completes successfully (status is threadpool.FINISHED) you
    will find the return value in `job.value`. If it raises an exception
    (status is threadpool.RAISED), you'll find it in `job.exception`, although
    the thread itself will not raise.

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

        self._done_event = threading.Event()

    def __repr__(self):
        if self.name:
            return f'<{self.status.name} Job {repr(self.name)}>'
        else:
            return f'<{self.status.name} Job on {self.function}>'

    def run(self):
        self.status = RUNNING
        try:
            self.value = self.function(*self.args, **self.kwargs)
            self.status = FINISHED
        except BaseException as exc:
            self.exception = exc
            self.status = RAISED

        if self.callback is not None:
            self.callback(self)

        self._done_event.set()

    def join(self):
        '''
        Block until this job runs and completes.
        '''
        self._done_event.wait()
