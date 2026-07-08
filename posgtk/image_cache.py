"""
posgtk/image_cache.py — Async product image loader with LRU + disk cache.

Scales images to 64×64 thumbnails. Downloads in background thread,
delivers pixbuf to main thread via GLib.idle_add.
"""

import hashlib
import os
import threading
import urllib.request
from collections import OrderedDict

from gi.repository import GdkPixbuf, GLib

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "thumbs")
MAX_MEMORY_ITEMS = 200
THUMB_SIZE = 64


class ImageCache:
    def __init__(self):
        self._mem_cache = OrderedDict()
        self._lock = threading.Lock()
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _disk_path(self, url):
        return os.path.join(CACHE_DIR, hashlib.md5(url.encode()).hexdigest() + ".png")

    def get(self, url, callback):
        with self._lock:
            if url in self._mem_cache:
                pb = self._mem_cache[url]
                self._mem_cache.move_to_end(url)
                callback(pb)
                return

        path = self._disk_path(url)
        if os.path.exists(path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, THUMB_SIZE, THUMB_SIZE)
                with self._lock:
                    self._mem_cache[url] = pb
                    if len(self._mem_cache) > MAX_MEMORY_ITEMS:
                        self._mem_cache.popitem(last=False)
                callback(pb)
                return
            except Exception:
                pass

        threading.Thread(target=self._download, args=(url, callback), daemon=True).start()

    def _download(self, url, callback):
        try:
            resp = urllib.request.urlopen(url, timeout=10)
            data = resp.read()
        except Exception:
            return

        path = self._disk_path(url)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return

        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, THUMB_SIZE, THUMB_SIZE)
            with self._lock:
                self._mem_cache[url] = pb
                if len(self._mem_cache) > MAX_MEMORY_ITEMS:
                    self._mem_cache.popitem(last=False)
            GLib.idle_add(callback, pb)
        except Exception:
            pass
