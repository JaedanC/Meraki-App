import json
from threading import Lock

from extra.api import RelaxedDictionary, safe_open_w


class Cache:
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            with open(self.file_path) as f:
                self._cache = RelaxedDictionary(json.load(f))
        except FileNotFoundError:
            self._cache = RelaxedDictionary({})
        
        self._lock = Lock()
    
    def set(self, keys, set_key, value):
        self._lock.acquire()
        self._cache.set(keys, set_key, value)
        with safe_open_w(self.file_path) as f:
            json.dump(self._cache.get_base(), f, indent=4)
        self._lock.release()
    
    def get(self, *keys, **kwargs):
        self._lock.acquire()
        found = self._cache.get(*keys, **kwargs)
        self._lock.release()
        return found
