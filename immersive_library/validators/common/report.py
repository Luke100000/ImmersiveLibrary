from databases import Database

from immersive_library.utils import refresh_precomputation
from immersive_library.validators.validator import Validator


class ReportValidator(Validator):
    # Here make a pre report and filter for valid reports,s optionally for moderator only
    async def post_report(self, database: Database, contentid: int, reason: str):
        await refresh_precomputation(database)

        content = await database.fetch_one(
            """
            SELECT *
            FROM content
                 INNER JOIN users ON content.userid = users.oid
                 INNER JOIN precomputation ON content.oid = precomputation.contentid

                 LEFT JOIN (SELECT reports.contentid, COUNT(*) as reports
                            FROM reports
                            WHERE reports.reason = 'INVALID'
                            GROUP BY reports.contentid) reported_c on reported_c.contentid = content.oid
            WHERE content.oid = :contentid AND 1.0 + likes / 10.0 - reported_c.reports < 0.0
        """,
            {"contentid": contentid},
        )

        if content:
            await database.execute(
                "INSERT INTO tags (contentid, tag) VALUES (:contentid, :tag)",
                {"contentid": contentid, "tag": "invalid"},
            )
