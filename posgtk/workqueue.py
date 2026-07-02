"""
gtk/workqueue.py — Background thread pool for async DB writes, printer, eBarimt, PAX.

UI never blocks on:
- DB writes (sale creation) — write() fires in ~5ms
- Printer IO (receipt printing) — async_op() runs in background
- eBarimt API (tax receipt) — async_op() runs in background
- PAX terminal (card payment) — async_op() runs in background

All results delivered to GTK main thread via GLib.idle_add().
"""

from concurrent.futures import ThreadPoolExecutor, Future
import logging
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib

logger = logging.getLogger("pos.gtk.workqueue")


class WorkQueue:
    def __init__(self, max_workers=4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pos-worker")
        self._futures = []
        self._futures_lock = threading.Lock()

    def _track(self, future):
        with self._futures_lock:
            self._futures.append(future)

        def _untrack(f):
            with self._futures_lock:
                try:
                    self._futures.remove(f)
                except ValueError:
                    pass
        future.add_done_callback(_untrack)

    def write(self, fn, *args, on_done=None, on_error=None, **kwargs):
        future = self._executor.submit(fn, *args, **kwargs)
        self._track(future)
        if on_done or on_error:
            def _wrapper(f):
                try:
                    result = f.result()
                    if on_done:
                        GLib.idle_add(on_done, result)
                except Exception as e:
                    logger.error(f"Worker failed: {e}")
                    if on_error:
                        GLib.idle_add(on_error, str(e))
            future.add_done_callback(_wrapper)
        return future

    def async_op(self, fn, *args, on_result=None, on_error=None, **kwargs):
        future = self._executor.submit(fn, *args, **kwargs)
        self._track(future)
        if on_result or on_error:
            def _w(f):
                try:
                    result = f.result()
                    if on_result:
                        GLib.idle_add(on_result, result)
                except Exception as e:
                    logger.error(f"Async op failed: {e}")
                    if on_error:
                        GLib.idle_add(on_error, str(e))
            future.add_done_callback(_w)
        return future

    def flush(self):
        with self._futures_lock:
            pending = list(self._futures)
        for f in pending:
            try:
                f.result(timeout=30)
            except Exception:
                pass

    def shutdown(self):
        self._executor.shutdown(wait=False)
        with self._futures_lock:
            for f in self._futures:
                f.cancel()
            self._futures.clear()
