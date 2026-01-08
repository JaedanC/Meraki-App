import datetime
import time
import traceback
from threading import Thread, Lock
from typing import List, Dict, Any, Callable

import pygui
from .cache import Cache


class Future:
    def __init__(
            self,
            request: Callable,
            args: List[Any],
            kwargs: Dict[str, Any],
            cache: Cache,
            lookup: str,
            default_on_fail: Any=None,
        ):
        self._request: Callable = request
        self._request_args = args
        self._request_kwargs = kwargs
        self._error_status = None
        self._lookup = lookup
        self._response = cache.get(lookup, "response")
        self._time = cache.get(lookup, "time")
        self._refreshing = False
        self._cache = cache
        self._default_on_fail = default_on_fail
        self._response_dirty = False
        self._queried_at_least_once = self._response is not None

    def draw_refresh_button(self, label: str, unique_id: str=None, **kwargs):
        unique_id = unique_id or label
        if self._refreshing:
            pygui.button(label + " " + "/-\|"[(pygui.get_frame_count() // 60) % 4] + "###" + unique_id)
        elif pygui.button(label + "###" + unique_id):
            self.begin_task(**kwargs)

        pygui.same_line()
        if self._time is not None:
            time_struct = datetime.datetime.fromtimestamp(self._time)
            pygui.text("Last refreshed: {}".format(time_struct.strftime("%d/%m/%Y, %H:%M:%S")))
        else:
            pygui.text("Last refreshed: Never")

    def is_response_new(self):
        return self._response_dirty

    def mark_response_used(self):
        self._response_dirty = False

    def response_exists(self):
        return self._response is not None

    def queried_at_least_once(self):
        return self._queried_at_least_once

    def response(self):
        return self._response

    def get_error_status(self):
        return self._error_status

    def get_last_updated(self):
        return self._time

    def _task(self, *args, **kwargs):
        try:
            self._response = self._request(
                *(list(self._request_args) + list(args)),
                **(self._request_kwargs | kwargs)
            )
            self._error_status = None
            self._time = time.time()
            self._cache.set([self._lookup], "response", self._response)
            self._cache.set([self._lookup], "time", self._time)
        except Exception as e:
            if self._default_on_fail is not None:
                self._response = self._default_on_fail
            else:
                self._response = None
                self._error_status = traceback.format_exc()
                raise e
        finally:
            self._refreshing = False
            self._response_dirty = True

    def begin_task(self, *args, **kwargs):
        if self._refreshing:
            return
        self._queried_at_least_once = True
        self._refreshing = True
        self.t = Thread(target=self._task, args=args, kwargs=kwargs)
        self.t.start()
