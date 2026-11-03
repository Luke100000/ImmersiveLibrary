import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

import orjson
import requests
from databases.interfaces import Record
from loguru import logger
from PIL import Image

from immersive_library.common import projects
from immersive_library.database import database
from immersive_library.enums import RenderPreset
from immersive_library.image_neighbors import add_image_neighbors
from immersive_library.previews import PRESET_SIZES, make_preview
from immersive_library.services import descriptions, embeddings
from immersive_library.services.openrouter import AssetError

# Only assets with at least this many likes are analyzed.
MIN_LIKES = int(os.getenv("ANALYSIS_MIN_LIKES", "0"))
BATCH_SIZE = 100
IMAGE_SIZE = PRESET_SIZES[RenderPreset.THUMBNAIL]


@dataclass(frozen=True)
class Step:
    name: str
    table: str
    column: str
    model: str
    # Whether assets of the project get this step.
    applies: Callable[[str], bool]
    # Derives the result from the asset and its preview.
    run: Callable[[Record, bytes], str | bytes]


STEPS = {
    step.name: step
    for step in (
        Step(
            "description",
            "content_descriptions",
            "description",
            descriptions.MODEL,
            descriptions.describes,
            lambda record, image: descriptions.describe_image(
                record["project"], image, descriptions.asset_context(record)
            ),
        ),
        Step(
            "embedding",
            "content_embeddings",
            "vector",
            embeddings.MODEL,
            embeddings.embeds,
            lambda record, image: embeddings.embed_image(image),
        ),
    )
}


@dataclass(frozen=True)
class Job:
    record: Record
    # The due steps, each with its dirty count when taken.
    dirty: dict[str, int]

    @property
    def content_id(self) -> int:
        return self.record["content_id"]


async def add_missing() -> None:
    """Adds dirty rows for assets without one."""
    for project in projects:
        for step in STEPS.values():
            if step.applies(project):
                await database.execute(
                    f"""
                    INSERT INTO {step.table} (content_id)
                    SELECT oid FROM content WHERE project = :project
                    ON CONFLICT DO NOTHING
                    """,
                    {"project": project},
                )


async def take_next(skip: set[int]) -> list[Job]:
    due = " UNION ALL ".join(
        f"SELECT content_id, '{step.name}' AS step, dirty FROM {step.table} WHERE dirty > 0"
        for step in STEPS.values()
    )
    records = await database.fetch_all(
        f"""
        SELECT c.oid AS content_id, c.project, c.title, c.meta,
               (SELECT json_group_array(tag) FROM (
                   SELECT tag FROM tags WHERE content_id=c.oid ORDER BY tag
               )) AS tags,
               json_group_object(due.step, due.dirty) AS dirty
        FROM ({due}) AS due
        JOIN content c ON c.oid = due.content_id
        JOIN precomputation p ON p.content_id = c.oid
        WHERE p.likes >= :min_likes
            AND c.oid NOT IN (SELECT value FROM json_each(:skip))
        GROUP BY c.oid
        ORDER BY p.likes DESC, c.oid
        LIMIT :limit
        """,
        {
            "min_likes": MIN_LIKES,
            "skip": orjson.dumps(sorted(skip)).decode(),
            "limit": BATCH_SIZE,
        },
    )
    return [Job(record, orjson.loads(record["dirty"])) for record in records]


async def finish(step: Step, job: Job, value=None, error: str | None = None) -> bool:
    """Stores the result, unless the asset changed meanwhile and stays dirty."""
    return bool(
        await database.fetch_val(
            f"""
            UPDATE {step.table}
            SET model=:model, {step.column}=:value, error=:error, dirty=0,
                updated_at=unixepoch()
            WHERE content_id=:id AND dirty=:dirty
            RETURNING 1
            """,
            {
                "id": job.content_id,
                "dirty": job.dirty[step.name],
                "model": step.model,
                "value": value,
                "error": error,
            },
        )
    )


def blank_preview() -> bytes:
    """The thumbnail of an empty render, to reject it before a paid request."""
    blank = BytesIO()
    Image.new("RGBA", IMAGE_SIZE).save(blank, format="PNG")
    return make_preview(blank.getvalue(), IMAGE_SIZE)


async def render(record, base_url: str, empty_preview: bytes) -> bytes:
    while True:
        response = await asyncio.to_thread(
            requests.get,
            f"{base_url}/v3/render/{record['project']}/{record['content_id']}",
            params={"preset": RenderPreset.THUMBNAIL.value},
            timeout=(10, 90),
        )
        if response.status_code != 429:
            break
        await asyncio.sleep(float(response.headers.get("Retry-After", 60)))

    if response.status_code == 404:
        raise AssetError("Render found no such asset")

    # A failed render, such as a browser timeout, is retried later.
    response.raise_for_status()
    if response.content == empty_preview:
        raise AssetError("Preview contains no visible asset")
    with Image.open(BytesIO(response.content)) as image:
        if image.size != IMAGE_SIZE:
            raise AssetError(f"Expected a {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]} preview")

    return response.content


async def analyze(job: Job, base_url: str, empty_preview: bytes) -> None:
    """Runs the due steps. An AssetError is stored; other errors are retried."""
    record = job.record
    due = []
    for name in job.dirty:
        step = STEPS[name]
        if step.applies(record["project"]):
            due.append(step)
        else:
            await finish(step, job)
    if not due:
        return

    try:
        image = await render(record, base_url, empty_preview)
    except AssetError as exc:
        logger.warning("Rendering {} failed: {}", job.content_id, exc)
        for step in due:
            await finish(step, job, error=str(exc))
        return

    for step in due:
        try:
            value = await asyncio.to_thread(step.run, record, image)
        except AssetError as exc:
            logger.warning("{} of {} failed: {}", step.name, job.content_id, exc)
            await finish(step, job, error=str(exc))
            continue
        stored = await finish(step, job, value)
        if stored and step.name == "embedding":
            await asyncio.to_thread(add_image_neighbors, job.content_id)

    logger.info("Analyzed {}/{}", record["project"], job.content_id)
