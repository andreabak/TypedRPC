"""Background threading base classes"""

from abc import ABC, abstractmethod
from threading import Event, Thread
from typing import Optional, Protocol, Any, Counter, Iterable, MutableMapping


__all__ = [
    "BackgroundServiceThreadBase",
    "BackgroundServiceThread",
    "StoppableThreadMain",
]


class BackgroundServiceThreadBase(ABC):
    """
    An abstract base class that implements basic interface and functionality for a background threaded service
    """
    def __init__(self, start: bool = False, safe_stop: bool = True):
        """
        Initialization for BackgroundServiceThreadBase
        :param start: if True the thread starts immediately after initialization.
                      Defaults to False
        :param safe_stop: if False makes the thread daemonic and doesn't wait for it to stop.
                      Defaults to True
        """
        self._stop_event: Event = Event()
        self._safe_stop: bool = safe_stop
        self._thread: Thread = self._create_thread()
        if start:
            self.start()

    @abstractmethod
    def _create_thread(self) -> Thread:
        """
        Abstract method to be overridden with a function that builds the thread
        :return: An initialized `Thread` instance
        """

    def start(self) -> None:
        """
        Starts the background thread
        """
        self._thread.start()

    def stop(self, wait: Optional[bool] = None) -> None:
        """
        Stops the background thread and waits for it to finish.
        :param wait: if True waits for the thread to stop, if False doesn't wait,
                     if omitted or None, honors `safe_stop`.
        """
        if wait is None:
            wait = self._safe_stop
        self._stop_event.set()
        if wait:
            self._thread.join()

    @property
    def safe_stop(self):
        """Whether the service will be safely stopped"""
        return self._safe_stop

    def __enter__(self) -> None:
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def __del__(self):
        self.stop()


class StoppableThreadMain(Protocol):
    """Typing Protocol for thread target (main) functions used by `BackgroundServiceThread`"""
    def __call__(self, *args: Any, stop_event: Optional[Event] = None, **kwargs: Any): ...


class BackgroundServiceThread(BackgroundServiceThreadBase):
    """
    Generic background service thread class
    """
    default_thread_name: str = 'BackgroundServiceThread'
    # noinspection PyTypeHints
    _services_count: Counter[str] = Counter()

    def __init__(self, *args: Any, exec_fn: StoppableThreadMain,
                 exec_args: Optional[Iterable[Any]] = None,
                 exec_kwargs: Optional[MutableMapping[str, Any]] = None,
                 thread_name: Optional[str] = None, **kwargs: Any):
        """
        Initialization for `BackgroundServiceThread`
        :param exec_fn: the thread's main function. Must accept a `stop_event` keyword argument
        :param exec_args: additional positional arguments for the thread's function
        :param exec_kwargs: additional keyword arguments for the thread's function
        :param thread_name: the thread's name. If not specified the class' default is used.
        :param args: additional positional arguments for `super().__init__(...)`
        :param kwargs: additional keyword arguments for `super().__init__(...)`
        """
        self._exec_fn: StoppableThreadMain = exec_fn
        self._exec_args: Iterable[Any] = exec_args or ()
        self._exec_kwargs: MutableMapping[str, Any] = exec_kwargs or {}
        if thread_name is None:
            thread_name = self.default_thread_name
        self._thread_name: Optional[str] = None
        self.thread_name = thread_name
        self.__class__._services_count[self.thread_name] += 1
        super().__init__(*args, **kwargs)

    @property
    def thread(self) -> Optional[Thread]:
        """The thread instance, None if not yet created"""
        return self._thread

    @property
    def thread_name(self) -> str:
        """The service thread's name"""
        if self._thread is not None:
            return self._thread.name
        return self._thread_name

    @thread_name.setter
    def thread_name(self, name: str):
        """Sets the service thread's name"""
        if self._thread_name is not None:
            self._services_count[self._thread_name] -= 1
        self._thread_name = name
        self._services_count[self.thread_name] += 1
        if self._thread is not None:
            self._thread.name = self._make_thread_name()

    def _make_thread_name(self) -> str:
        """Helper function to generate the final thread's name"""
        assert self._thread_name is not None
        same_name_count: int = self._services_count[self._thread_name]
        same_name_postfix: str = f'-{same_name_count}' if same_name_count else ""
        return self._thread_name + same_name_postfix

    def _create_thread(self) -> Thread:
        return Thread(
            target=self._exec_fn,
            args=self._exec_args,
            kwargs={**self._exec_kwargs, 'stop_event': self._stop_event},
            name=self._make_thread_name(),
            daemon=(not self._safe_stop)
       )
