from fastapi import HTTPException

from immersive_library.common import projects
from immersive_library.database import database
from immersive_library.models import Collection, CollectionCreate, CollectionUpdate
from immersive_library.utils import content_guard

COLLECTION_SELECT = """
    SELECT collections.oid AS collection_id, collections.user_id, users.username,
           collections.project, collections.title, collections.description,
           collections.is_public, collections.created_at,
           COALESCE(collections.user_id = :viewer_id, 0) AS is_owner,
           (SELECT COUNT(*) FROM collection_items
            WHERE collection_id=collections.oid) AS content_count,
           CASE WHEN :content_id IS NOT NULL THEN EXISTS (
               SELECT 1 FROM collection_items
               WHERE collection_id=collections.oid AND content_id=:content_id
           ) END AS contains_content
    FROM collections JOIN users ON users.oid=collections.user_id
"""


async def list_collections(
    project: str,
    user_id: int | None = None,
    q: str | None = None,
    content_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer_id: int | None = None,
) -> list[Collection]:
    if content_id is not None:
        await content_guard(project, content_id)

    query = (
        COLLECTION_SELECT
        + """
        WHERE collections.project=:project
        AND (collections.user_id=:viewer_id OR collections.is_public=1)
    """
    )
    values = {
        "project": project,
        "viewer_id": viewer_id,
        "content_id": content_id,
        "limit": limit,
        "offset": offset,
    }
    if user_id is not None:
        query += " AND collections.user_id=:user_id"
        values["user_id"] = user_id

    if q and q.strip():
        query += """
            AND (collections.title LIKE :q OR collections.description LIKE :q
                 OR users.username LIKE :q)
        """
        values["q"] = f"%{q.strip()}%"

    query += " ORDER BY collections.oid DESC LIMIT :limit OFFSET :offset"
    records = await database.fetch_all(query, values)
    return [Collection(**dict(record)) for record in records]


async def get_collection(
    project: str, collection_id: int, viewer_id: int | None
) -> Collection:
    record = await database.fetch_one(
        COLLECTION_SELECT
        + """
            WHERE collections.project=:project AND collections.oid=:collection_id
            AND (collections.user_id=:viewer_id OR collections.is_public=1)
        """,
        {
            "project": project,
            "collection_id": collection_id,
            "viewer_id": viewer_id,
            "content_id": None,
        },
    )
    if record is None:
        raise HTTPException(404, "Collection not found")
    return Collection(**dict(record))


async def require_owner(project: str, collection_id: int, user_id: int) -> Collection:
    collection = await get_collection(project, collection_id, user_id)
    if not collection.is_owner:
        raise HTTPException(403, "Only the collection owner can change it")
    return collection


async def create_collection(
    project: str, collection: CollectionCreate, user_id: int
) -> Collection:
    if project not in projects and not await database.fetch_val(
        "SELECT 1 FROM content WHERE project=:project LIMIT 1", {"project": project}
    ):
        raise HTTPException(404, "Project not found")

    collection_id = await database.execute(
        """
        INSERT INTO collections (user_id, project, title, description, is_public)
        VALUES (:user_id, :project, :title, :description, :is_public)
        """,
        {"user_id": user_id, "project": project, **collection.model_dump()},
    )
    return await get_collection(project, collection_id, user_id)


async def update_collection(
    project: str, collection_id: int, changes: CollectionUpdate, user_id: int
) -> Collection:
    async with database.transaction():
        await database.execute(
            """
            UPDATE collections
            SET title=COALESCE(:title, title),
                description=COALESCE(:description, description),
                is_public=COALESCE(:is_public, is_public),
                updated_at=unixepoch()
            WHERE oid=:collection_id AND project=:project AND user_id=:user_id
            """,
            {
                "collection_id": collection_id,
                "project": project,
                "user_id": user_id,
                **changes.model_dump(),
            },
        )
        return await require_owner(project, collection_id, user_id)


async def delete_collection(project: str, collection_id: int, user_id: int) -> None:
    async with database.transaction():
        deleted = await database.fetch_val(
            """
            DELETE FROM collections
            WHERE oid=:collection_id AND project=:project AND user_id=:user_id
            RETURNING oid
            """,
            {"collection_id": collection_id, "project": project, "user_id": user_id},
        )
        if deleted is None:
            await require_owner(project, collection_id, user_id)


async def set_membership(
    project: str, collection_id: int, content_id: int, user_id: int, included: bool
) -> None:
    async with database.transaction():
        if included:
            statement = """
                INSERT INTO collection_items (collection_id, content_id)
                SELECT collections.oid, content.oid FROM collections JOIN content
                    ON content.project=collections.project
                WHERE collections.oid=:collection_id AND collections.project=:project
                    AND collections.user_id=:user_id AND content.oid=:content_id
                ON CONFLICT (collection_id, content_id) DO NOTHING
            """
        else:
            statement = """
                DELETE FROM collection_items
                WHERE collection_id=:collection_id AND content_id=:content_id
                AND EXISTS (
                    SELECT 1 FROM collections
                    WHERE oid=:collection_id AND project=:project AND user_id=:user_id
                )
            """

        await database.execute(
            statement,
            {
                "project": project,
                "collection_id": collection_id,
                "content_id": content_id,
                "user_id": user_id,
            },
        )
        await require_owner(project, collection_id, user_id)
        if included:
            await content_guard(project, content_id)
