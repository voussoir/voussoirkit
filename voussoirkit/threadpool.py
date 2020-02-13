import threading

from voussoirkit import sentinel

PENDING = 'pending'
RUNNING = 'running'
FINISHED = 'finished'
RAISED = 'raised'

NO_RETURN = sentinel.Sentinel('NO_RETURN', truthyness=False)
NO_EXCEPTION = sentinel.Sentinel('NO_EXCEPTION', truthyness=False)

class ThreadPoolException(Exception):
    pass

class PoolClosed(ThreadPoolException):
    pass

class ThreadPool:
    def __init__(self, size, paused=False):
        '''
        paused:
            The pool will start in a paused state and you will have to call
            `clear_done_and_start_jobs` to start it.
        '''
        if not isinstance(size, int):
            raise TypeError(f'size must be an int, not {type(size)}.')
        if size < 1:
            raise ValueError(f'size must be >= 1, not {size}.')
        self.max_size = size
        self.closed = False
        self.paused = paused
        self.jobs = []
        self.job_manager_lock = threading.Lock()

    def _clear_done_jobs(self):
        '''
        This function assumes that job_manager_lock is acquired!!
        You should call clear_done_and_start_jobs instead!
        '''
        self.jobs[:] = [j for j in self.jobs if j.status in {PENDING, RUNNING}]

    def _start_jobs(self):
        '''
        This function assumes that job_manager_lock is acquired!!
        You should call clear_done_and_start_jobs instead!
        '''
        available = self.max_size - self.running_count()
        available = max(0, available)
        if available == 0:
            return
        # print(f'Gonna start me some {available} jobs.')
        for job in list(self.jobs):
            if job.status == PENDING:
                # print('starting', job)
                job.start()
                available -= 1
                if available == 0:
                    break

    def _clear_done_and_start_jobs(self):
        '''
        This function assumes that job_manager_lock is acquired!!
        You should call clear_done_and_start_jobs instead!
        '''
        self._clear_done_jobs()
        self._start_jobs()

    def _job_finished(self):
        '''
        When a job finishes, it will call here.
        '''
        if self.paused:
            return

        self.clear_done_and_start_jobs()

    def assert_not_closed(self):
        '''
        If the pool is closed (because you called `join`), raise PoolClosed.
        Otherwise do nothing.
        '''
        if self.closed:
            raise PoolClosed()

    def add(self, function, *, name=None, args=tuple(), kwargs=dict()):
        '''
        Add a new job to the pool. Jobs are run in the order they are added.

        Don't forget that in order to write a tuple of length 1 you must still
        add a comma on the end. `add(print, args=(4))` is an error, you need to
        `add(print, args=(4,))` or use a list instead: `add(print, args=[4])`.

        name:
            An optional value that will appear in the repr of the job and
            has no other purpose. Use this if you intend to print(job) and want
            a human friendly name string.
        '''
        self.assert_not_closed()
        self.job_manager_lock.acquire()

        job = Job(
            pool=self,
            function=function,
            name=name,
            args=args,
            kwargs=kwargs,
        )
        self.jobs.append(job)

        if not self.paused:
            self._clear_done_and_start_jobs()

        self.job_manager_lock.release()
        return job

    def clear_done_and_start_jobs(self):
        '''
        Remove finished and raised jobs from the queue and start some new jobs.

        The job queue is maintained automatically while adding new jobs and
        when a job finishes, as long as the pool is not paused, so you should
        not have to call it yourself. If you do pause the pool, use this method
        to restart it.

        Because the pool's internal job queue is flushed regularly, you should
        store your own references to jobs to get their return values.
        '''
        self.job_manager_lock.acquire()
        self._clear_done_and_start_jobs()
        self.paused = False
        self.job_manager_lock.release()

    def join(self):
        '''
        Permanently close the pool, preventing any new jobs from being added,
        and block until all jobs are complete.
        '''
        self.closed = True
        self.clear_done_and_start_jobs()
        for job in self.jobs:
            job.join()

    def running_count(self):
        return sum(1 for job in list(self.jobs) if job.status is RUNNING)

    def unfinished_count(self):
        return sum(1 for job in list(self.jobs) if job.status in {PENDING, RUNNING})

class Job:
    def __init__(self, pool, function, *, name=None, args=tuple(), kwargs=dict()):
        self.pool = pool
        self.name = name
        self.status = PENDING
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.value = NO_RETURN
        self.exception = NO_EXCEPTION
        self._thread = None

        # joinme_lock works because it is possible for a single thread to block
        # itself by calling `lock.acquire()` twice. The first call is here,
        # and the second call is in `join` so that join will block until the
        # lock is released by the job's finishing phase.
        self.joinme_lock = threading.Lock()
        self.joinme_lock.acquire()

    def __repr__(self):
        if self.name:
            return f'<{self.status} Job {repr(self.name)}>'
        else:
            return f'<{self.status} Job on {self.function}>'

    def join(self):
        '''
        Block until this job runs and completes.
        '''
        self.joinme_lock.acquire()
        self.joinme_lock.release()

    def start(self):
        '''
        Start the job. If the function completes successfully you will find the
        return value in `value`. If it raises an exception, you'll find it in
        `exception`, although the thread itself will not raise.
        '''
        def do_it():
            try:
                self.value = self.function(*self.args, **self.kwargs)
                self.status = FINISHED
            except Exception as exc:
                # print(exc)
                self.exception = exc
                self.status = RAISED
            self._thread = None
            self.pool._job_finished()
            self.joinme_lock.release()

        self.status = RUNNING
        self._thread = threading.Thread(target=do_it)
        self._thread.daemon = True
        self._thread.start()
