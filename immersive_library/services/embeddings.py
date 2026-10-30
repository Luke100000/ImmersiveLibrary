import numpy as np

from immersive_library.common import projects
from immersive_library.services.openrouter import image_url, post

MODEL = "amazon/titan-embed-image-v1"
DIMENSIONS = 384


def embeds(project_name: str) -> bool:
    return project_name in projects


def quantize(vector: list[float]) -> bytes:
    """Scales to int8. Cosine ignores length, so the scale is dropped."""
    values = np.asarray(vector, dtype=np.float32)
    return np.round(values / np.abs(values).max() * 127).astype(np.int8).tobytes()


def embed_image(image: bytes) -> bytes:
    result = post(
        "embeddings",
        {
            "model": MODEL,
            "dimensions": DIMENSIONS,
            "input": [
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url(image)}}
                    ]
                }
            ],
        },
    )
    return quantize(result["data"][0]["embedding"])
