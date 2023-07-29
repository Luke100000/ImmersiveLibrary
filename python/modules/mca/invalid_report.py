from modules.module import Module
from utils import get_base_select


class InvalidReport(Module):
    async def post_report(self, contentid: int, reason: str):
        prompt = get_base_select(False, "INVALID")

        prompt += (
            "WHERE c.oid = :contentid AND 1.0 + likes / 10.0 - reports + counter_reports * 10.0 < 0.0"
        )

        content = await self.database.fetch_one(prompt, {"contentid": contentid})

        if content:
            print(content)

            await self.database.execute(
                "INSERT INTO tags (contentid, tag) VALUES (:contentid, :tag)",
                {"contentid": contentid, "tag": "invalid"},
            )
