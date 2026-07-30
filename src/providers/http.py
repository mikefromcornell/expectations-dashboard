"""Polite HTTP with retry/backoff and on-disk caching.

The sandbox that designed this got HTTP 429 from Yahoo on every request, which
is exactly why retry + fallback + last-good cache are mandatory rather than nice
to have (PRD §4, §5.7).
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from ..config import BROWSER_UA, ROOT

_CURL = shutil.which("curl")


def _curl_get(url: str, headers: dict, timeout: int) -> tuple[int, str]:
    """Fallback transport.

    Some providers (Yahoo, SEC) fingerprint the TLS handshake and return
    429/403 to python-requests while serving curl normally. Shelling out to
    curl is ugly but it is the difference between a working dashboard and an
    empty one, so it stays as a documented last resort.
    """
    if not _CURL:
        raise FetchError("curl transport unavailable")
    cmd = [_CURL, "-sS", "--compressed", "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    if p.returncode != 0:
        raise FetchError(f"curl exit {p.returncode}: {p.stderr[:120]}")
    body, _, code = p.stdout.rpartition("\n")
    return int(code or 0), body

CACHE_DIR = ROOT / ".httpcache"
CACHE_DIR.mkdir(exist_ok=True)

_SESSION = requests.Session()


class FetchError(RuntimeError):
    pass


def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")


def read_cache(url: str, max_age_s: float | None = None) -> Any | None:
    p = _cache_path(url)
    if not p.exists():
        return None
    if max_age_s is not None and (time.time() - p.stat().st_mtime) > max_age_s:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def write_cache(url: str, payload: Any) -> None:
    try:
        _cache_path(url).write_text(json.dumps(payload))
    except Exception:
        pass


def get_json(
    url: str,
    *,
    headers: dict | None = None,
    tries: int = 4,
    timeout: int = 20,
    cache_s: float | None = None,
    fallback_to_cache: bool = True,
) -> Any:
    """GET JSON with exponential backoff + jitter. Falls back to last-good cache."""
    if cache_s:
        hit = read_cache(url, cache_s)
        if hit is not None:
            return hit

    h = {"User-Agent": BROWSER_UA, "Accept": "application/json"}
    if headers:
        h.update(headers)

    last: Exception | None = None
    for attempt in range(tries):
        # alternate transports: requests first, then curl (different TLS fingerprint)
        use_curl = attempt % 2 == 1
        try:
            if use_curl:
                code, body = _curl_get(url, h, timeout)
                if code == 429:
                    raise FetchError("HTTP 429 rate limited (curl)")
                if code >= 400:
                    raise FetchError(f"HTTP {code} (curl)")
                if not body.strip():
                    raise FetchError("empty body (curl)")
                data = json.loads(body)
            else:
                r = _SESSION.get(url, headers=h, timeout=timeout)
                if r.status_code == 429:
                    raise FetchError("HTTP 429 rate limited")
                r.raise_for_status()
                if not r.content:
                    raise FetchError("empty body")
                data = r.json()
            write_cache(url, data)
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < tries - 1:
                time.sleep((2**attempt) * 0.6 + random.random() * 0.4)

    if fallback_to_cache:
        stale = read_cache(url, None)
        if stale is not None:
            return stale
    raise FetchError(f"{url} failed after {tries} tries: {last}")


def get_text(url: str, *, headers: dict | None = None, tries: int = 3, timeout: int = 20,
             prefer_curl: bool = False) -> str:
    """prefer_curl flips the transport order for hosts that stall python-requests
    but serve curl instantly (FRED is one)."""
    h = {"User-Agent": BROWSER_UA}
    if headers:
        h.update(headers)
    last: Exception | None = None
    for attempt in range(tries):
        use_curl = (attempt % 2 == 0) if prefer_curl else (attempt % 2 == 1)
        try:
            if use_curl:
                code, body = _curl_get(url, h, timeout)
                if code >= 400:
                    raise FetchError(f"HTTP {code} (curl)")
                if not body.strip():
                    raise FetchError("empty body (curl)")
                return body
            r = _SESSION.get(url, headers=h, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < tries - 1:
                time.sleep((2**attempt) * 0.6 + random.random() * 0.4)
    raise FetchError(f"{url} failed: {last}")
