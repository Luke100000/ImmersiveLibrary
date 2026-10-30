import base64
import os

import requests

API_URL = "https://openrouter.ai/api/v1"

# Statuses that reject the input itself. Others are temporary.
REJECTED_STATUSES = {400, 403, 413, 422}


class AssetError(Exception):
    """The input itself fails, so retrying it is pointless."""


def image_url(image: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image).decode()


def post(path: str, payload: dict) -> dict:
    response = requests.post(
        f"{API_URL}/{path}",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json=payload,
        timeout=(10, 180),
    )
    result = response.json()
    if response.status_code in REJECTED_STATUSES:
        raise AssetError(f"Rejected with HTTP {response.status_code}: {result}")
    if "error" in result:
        raise RuntimeError(result["error"]["message"])
    response.raise_for_status()
    return result
