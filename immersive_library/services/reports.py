from fastapi import HTTPException

from immersive_library.common import get_project
from immersive_library.database import database
from immersive_library.utils import content_guard, is_moderator, update_precomputation

# Reports relative to likes. Content is hidden once it exceeds 1.
REPORT_SCORE = "precomputation.reports * 10.0 / (precomputation.likes + 10)"

# Content of a collection the viewer can see: not banned, hidden or reported by them.
COLLECTION_CONTENT_VISIBILITY = f"""
    c.project=:project AND NOT author.banned AND {REPORT_SCORE} <= 1
    AND NOT EXISTS (
        SELECT 1 FROM reports WHERE reports.content_id=c.oid
            AND reports.user_id=:viewer_id AND reports.reason='DEFAULT'
    )
"""


async def can_see_hidden(viewer_id: int | None) -> bool:
    return viewer_id is not None and await is_moderator(database, viewer_id)


async def visible_content_guard(
    project: str, content_id: int, viewer_id: int | None
) -> None:
    """Hidden content looks deleted to everyone but its author and moderators."""
    visible = await database.fetch_val(
        f"""
        SELECT 1 FROM content AS c
        JOIN users ON users.oid = c.user_id
        LEFT JOIN precomputation ON precomputation.content_id = c.oid
        WHERE c.oid = :content_id AND c.project = :project AND (
            NOT users.banned AND COALESCE({REPORT_SCORE}, 0) <= 1
            OR c.user_id = :viewer_id
            OR EXISTS (SELECT 1 FROM users AS viewer WHERE viewer.oid = :viewer_id AND viewer.moderator)
        )
        """,
        {"content_id": content_id, "project": project, "viewer_id": viewer_id},
    )
    if not visible:
        raise HTTPException(404, "Content not found")


async def set_report(
    project: str, content_id: int, user_id: int, reason: str, reported: bool
) -> bool:
    await content_guard(project, content_id)

    report_reason = get_project(project).report_reasons.get(reason)
    if report_reason is None:
        raise HTTPException(400, "Unknown report reason")
    if report_reason.moderator_only and not await is_moderator(database, user_id):
        raise HTTPException(403, "Not a moderator")

    if reported:
        await get_project(project).validate(
            "pre_report", database, user_id, content_id, reason
        )

    async with database.transaction():
        if reported:
            statement = """
                INSERT INTO reports (user_id, content_id, reason)
                SELECT :user_id, :content_id, :reason FROM content WHERE oid=:content_id AND project=:project
                ON CONFLICT (user_id, content_id, reason) DO NOTHING RETURNING user_id
            """
        else:
            statement = """
                DELETE FROM reports WHERE user_id=:user_id AND content_id=:content_id AND reason=:reason
                AND EXISTS (SELECT 1 FROM content WHERE oid=:content_id AND project=:project)
                RETURNING user_id
            """

        changed = (
            await database.fetch_val(
                statement,
                {
                    "user_id": user_id,
                    "content_id": content_id,
                    "reason": reason,
                    "project": project,
                },
            )
            is not None
        )

        await content_guard(project, content_id)

        if changed:
            if reported:
                await get_project(project).call(
                    "post_report", database, user_id, content_id, reason
                )
            await update_precomputation(database, content_id)

    return changed
