from databases import Database

from immersive_library.utils import update_precomputation
from immersive_library.validators.validator import Validator


class InvalidReportValidator(Validator):
    async def post_report(
        self, database: Database, user_id: int, content_id: int, reason: str
    ):
        content = await database.fetch_one(
            """
            SELECT *
            FROM content
                     INNER JOIN users ON content.user_id = users.oid
                     INNER JOIN precomputation ON content.oid = precomputation.content_id

                     LEFT JOIN (SELECT reports.content_id, COUNT(*) as reports
                                FROM reports
                                WHERE reports.reason = 'INVALID'
                                GROUP BY reports.content_id) reported_c on reported_c.content_id = content.oid
            WHERE content.oid = :content_id
              AND 1.0 + likes / 10.0 - reported_c.reports < 0.0
            """,
            {"content_id": content_id},
        )

        if content:
            await database.execute(
                """
                INSERT INTO tags (content_id, tag) VALUES (:content_id, :tag)
                ON CONFLICT (content_id, tag) DO NOTHING
                """,
                {"content_id": content_id, "tag": "invalid"},
            )

            await update_precomputation(database, content_id)
