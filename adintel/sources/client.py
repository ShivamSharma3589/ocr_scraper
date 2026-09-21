"""HTTP clients for the two vendors, with key rotation and retries."""

import itertools
import time

import requests

from adintel.config import settings


class ApiError(RuntimeError):
    pass


class SearchApiClient:
    def __init__(self, keys=None):
        keys = keys or settings.SEARCH_API_KEYS
        if not keys:
            raise ApiError("SEARCH_API_KEYS is empty")
        self._keys = itertools.cycle(keys)
        self.calls = 0

    def get(self, params, attempts=3):
        last = None
        for attempt in range(1, attempts + 1):
            payload = {k: v for k, v in params.items() if v is not None}
            payload["api_key"] = next(self._keys)
            try:
                response = requests.get(
                    settings.SEARCHAPI_URL, params=payload,
                    timeout=settings.REQUEST_TIMEOUT,
                )
                self.calls += 1
                data = response.json()
            except Exception as exc:
                last = exc
                time.sleep(attempt)
                continue

            error = data.get("error")
            if error:
                if "didn't return any results" in str(error):
                    return {}
                last = ApiError(str(error))
                time.sleep(attempt)
                continue
            return data

        raise ApiError(f"SearchAPI failed after {attempts} attempts: {last}")


class SerpApiClient:
    def __init__(self, key=None):
        self.key = key or settings.SERP_API_KEY
        if not self.key:
            raise ApiError("SERP_API_KEY is empty")
        self.calls = 0

    def get(self, params, attempts=3):
        last = None
        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(
                    settings.SERPAPI_URL, params=dict(params, api_key=self.key),
                    timeout=settings.REQUEST_TIMEOUT,
                )
                self.calls += 1
                data = response.json()
            except Exception as exc:
                last = exc
                time.sleep(attempt)
                continue

            if data.get("error"):
                last = ApiError(str(data["error"]))
                time.sleep(attempt)
                continue
            return data

        raise ApiError(f"SerpApi failed after {attempts} attempts: {last}")
