import shutil
import typing

from voussoirkit import bytestring
from voussoirkit import pipeable
from voussoirkit import ratelimiter
from voussoirkit import sentinel
from voussoirkit import stringtools
from voussoirkit import vlogging

log = vlogging.get_logger(__name__, 'progressbars')

# Base class #######################################################################################

DONE = sentinel.Sentinel('done')

class Progress:
    def __init__(self, total=None, *, topic=None):
        raise NotImplementedError

    def done(self) -> None:
        '''
        Shortcut method for step(value=DONE).

        Should bypass any rendering ratelimits that might be in place, to ensure
        that the progress bar's final state on screen is the done state.

        Should be idempotent with additional calls to done().

        Should not cause duplicate rendering in the case that step(value>=total)
        was called before done() was called.
        '''
        self.step(DONE)

    def set_topic(self, topic: typing.Union[str, None]) -> None:
        '''
        The topic string might be the name of a file being copied / downloaded,
        the title of the function being run, or any other description of what
        the progress bar represents.

        topic must not be any other type. Defensive implementations should
        prepare to receive any other type and e.g. treat them as None.

        topic should not be used for "reticulating splines" text spinners. That
        should be implemented as a class which shows text messages on each step.

        The implementation might show the topic directly next to the progress
        bar or somewhere else entirely. It might not show the topic at all.
        '''
        raise NotImplementedError

    def set_total(self, total: typing.Union[int, float, None]) -> None:
        '''
        All implementations must be prepared to handle int, float, and None.
        Implementations might switch from determinate modes to indeterminate
        modes and vice versa.

        total must be greater than 0. Defensive implementations should prepare
        to receive nonpositive totals.

        total must not be any other type. Defensive implementations should
        prepare to receive other types and e.g. treat them as indeterminate.
        '''
        raise NotImplementedError

    def step(self, value: typing.Union[int, float]) -> None:
        '''
        Increment the state of the progressbar to this new value.

        Some implementations may not use the value in their rendering
        whatsoever, e.g. spinners, but if total is not None then value should
        try to be relevant.

        Most implementations will benefit from a ratelimiter that only shows a
        certain number of status updates per second, since very rapid updates
        can be expensive with diminishing usefulness. However, if the value DONE
        is given, that should probably bypass the ratelimiter.

        value must not be any other type. Defensive implementations should
        prepare to receive other types and e.g. re-render the previously used
        value or ignore them.

        value must be greater than or equal to 0. Defensive implementations
        should prepare to receive negative values and e.g. clamp to 0.

        In general, value should be less than or equal to total. Defensive
        implementations should prepare to receive higher values and e.g. clamp
        to total or continue counting beyond 100%.
        '''
        raise NotImplementedError

# Implementations ##################################################################################

WIDTH_AUTO = sentinel.Sentinel('width auto')
DEFAULT_RATELIMIT = 8
DEFAULT_TOTAL_TOSTRING = lambda total: '?' if total is None else str(total)
DEFAULT_VALUE_TOSTRING = lambda value, total=0, total_string='': str(value).rjust(len(total_string))

class Bar1(Progress):
    def __init__(
            self,
            total=None,
            *,
            ratelimit=DEFAULT_RATELIMIT,
            show_topic=True,
            topic=None,
            total_tostring=None,
            value_tostring=None,
            width=WIDTH_AUTO,
        ):
        if not should_stderr():
            self.step = do_nothing

        self.total = None
        self._last_value = 0

        self.solid_char = '#'
        self.blank_char = '.'

        self.ratelimiter = normalize_ratelimiter(ratelimit)

        if width is WIDTH_AUTO:
            self.width = shutil.get_terminal_size().columns - 2
            self.width = min(80, self.width)
        else:
            self.width = width

        self.total_tostring = total_tostring or DEFAULT_TOTAL_TOSTRING
        self.value_tostring = value_tostring or DEFAULT_VALUE_TOSTRING

        self.show_topic = show_topic
        self._set_topic(topic)
        self.set_total(total)

    def _set_topic(self, topic):
        if not self.show_topic:
            topic = None

        if isinstance(topic, str):
            self.topic = topic
            self.topic_render = topic + ' '
        else:
            self.topic = ''
            self.topic_render = ''

    def set_topic(self, topic):
        self._set_topic(topic)
        self._set_total(self.total)

    def _set_total(self, total):
        if total is not None and not isinstance(total, (int, float)):
            log.warning(f'Bar1.set_total does not understand {total}, falling back to None.')
            total = None

        if total is None:
            self._ind_animation_index = 0

        self.total = total

        self.total_string = self.total_tostring(total)
        self.total_string_width = stringtools.unicode_width(self.total_string)

        if self.total is None:
            value_example = 0
        else:
            value_example = total
        value_example = self.value_tostring(value_example)
        value_width = max(stringtools.unicode_width(value_example), self.total_string_width)

        self.bar_width = self.width
        self.bar_width -= self.total_string_width
        self.bar_width -= value_width
        if self.topic:
            self.bar_width -= (stringtools.unicode_width(self.topic))
            # Space between topic and bar.
            self.bar_width -= 1
        # Spaces on either side of the bar.
        self.bar_width -= 2
        self.bar_width = max(self.bar_width, 1)

        if self.total is not None:
            self.value_per_block = self.total / self.bar_width

    def set_total(self, total):
        self._set_total(total)
        self._done = False

    def _render_line(self, value):
        value_string = self.value_tostring(value, self.total, self.total_string)

        if self._done:
            bar = self.solid_char * self.bar_width
        elif self.total is None:
            bar = (self.blank_char * self._ind_animation_index) + self.solid_char
            bar = bar.ljust(self.bar_width, self.blank_char)
            self._ind_animation_index = (self._ind_animation_index + 1) % self.bar_width
        else:
            solid_count = round(value / self.value_per_block)
            bar = (self.solid_char * solid_count).ljust(self.bar_width, self.blank_char)

        return f'{self.topic_render}{value_string} {bar} {self.total_string}'

    def step(self, value):
        if value is not DONE and not isinstance(value, (int, float)):
            log.warning('ProgressBar.step received a non-numeric argument %s.', value)
            return

        if value is DONE:
            if self._done:
                return
            if self.total is not None:
                value = self.total
            else:
                value = self._last_value
            self._done = True
        elif self.total is not None and value >= self.total:
            self._done = True
        else:
            self._done = False
            if self.ratelimiter and self.ratelimiter.limit(1) is False:
                return

        line = self._render_line(value)
        end = '\n' if self._done else '\r'
        pipeable.stderr(line, end=end)
        self._last_value = value

class DoNothing(Progress):
    '''
    You can use this when you don't want to use a real progress bar class, but
    you don't want to use a None and preface everything with `if not None`.
    '''
    def __init__(self, *args, **kwargs):
        self.done = do_nothing
        self.set_total = do_nothing
        self.set_topic = do_nothing
        self.step = do_nothing

# Common presets ###################################################################################

def total_tostring_bytestring(**kwargs):
    def total_tostring(total):
        if total is None:
            return '?'
        return bytestring.bytestring(total, **kwargs)
    return total_tostring

def value_tostring_bytestring(**kwargs):
    decimals = kwargs.get('decimal_places', 3)
    just = 8 + decimals + (1 if decimals else 0)
    def value_tostring(value, total=0, total_string=''):
        # The longest possible output looks like "1000.00 mib".
        return bytestring.bytestring(value, **kwargs).rjust(just, ' ')
    return value_tostring

def total_tostring_comma(total):
    if total is None:
        return '?'
    return f'{total:,}'

def value_tostring_comma(value, total=0, total_string=''):
    return f'{value:,}'.rjust(len(total_string))

def bar1_comma(*args, **kwargs):
    return Bar1(
        *args,
        total_tostring=total_tostring_comma,
        value_tostring=value_tostring_comma,
        **kwargs,
    )

def bar1_bytestring(*args, **kwargs):
    return Bar1(
        *args,
        total_tostring=total_tostring_bytestring(),
        value_tostring=value_tostring_bytestring(),
        **kwargs,
    )

# Helper functions #################################################################################

def do_nothing(*args, **kwargs):
    return

def normalize(progressbar, total=None, *, topic=None) -> typing.Union[Progress, None]:
    if progressbar is None:
        return None

    elif isinstance(progressbar, Progress):
        progressbar.set_total(total=total)
        progressbar.set_topic(topic=topic)
        return progressbar

    elif callable(progressbar):
        return progressbar(total=total, topic=topic)

    raise TypeError(f'Could not normalize {progressbar} into a Progress instance.')

normalize_progressbar = normalize

def normalize_ratelimiter(ratelimit):
    if ratelimit is None:
        return None
    elif isinstance(ratelimit, (int, float)):
        return ratelimiter.Ratelimiter(allowance=ratelimit, mode='reject')
    elif isinstance(ratelimit, ratelimiter.Ratelimiter):
        return ratelimit

def should_stderr():
    '''
    Returns whether stderr exists and is suitable for printing a progress bar.

    If the return value of this function is False, then there is no point
    using a progressbar class.
    '''
    return pipeable.stderr_tty()
