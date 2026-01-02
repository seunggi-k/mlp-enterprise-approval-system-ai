import time
from typing import Any
from urllib.parse import urlparse

import httpx


def validate_callback_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("callbackUrl은 http/https만 허용합니다.")
    # TODO: 내부망 주소만 허용하도록 allowlist/검증 추가
    return url


def post_with_retry(callback_url: str, callback_key: str, payload: dict[str, Any], timeout: float = 10.0):
    """
    POST callback with retries. Raises the last error if all attempts fail.
    """
    delays = [0.0, 0.5, 1.0, 2.0]  # 첫 시도 + 최대 3회 재시도
    last_error: Exception | None = None
    headers = {
        "X-AI-CALLBACK-KEY": callback_key,
        "Content-Type": "application/json",
    }

    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            with httpx.Client(timeout=timeout) as http:
                res = http.post(callback_url, headers=headers, json=payload)
            print(f"[CALLBACK] attempt={attempt} status={res.status_code} url={callback_url}")
            res.raise_for_status()
            return
        except Exception as e:
            last_error = e
            print(f"[CALLBACK] attempt={attempt} failed: {e}")

    print(f"[CALLBACK] all retries failed url={callback_url}")
    if last_error:
        raise last_error
