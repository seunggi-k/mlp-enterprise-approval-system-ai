import httpx

from app.core.config import settings


def format_callback_url(raw: str, meet_no: int) -> str:
    if "{meetNo}" in raw:
        return raw.replace("{meetNo}", str(meet_no))
    return raw


def callback_to_spring(callback_url: str, callback_key: str, payload: dict):
    headers = {settings.CALLBACK_HEADER: callback_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as http:
        r = http.patch(callback_url, headers=headers, json=payload)
        print("✅ CALLBACK REQ URL:", callback_url)
        print("✅ CALLBACK RES:", r.status_code, r.text)
        r.raise_for_status()
