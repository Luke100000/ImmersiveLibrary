from modules.module import Module
from utils import get_base_select


class InvalidReport(Module):
    async def post_report(self, contentid: int, reason: str):
        prompt = get_base_select(False, "INVALID")

        prompt += "WHERE 1.0 + likes / 10.0 - reports < 0.0"

        content = await self.database.fetch_all(prompt)

        for oid in content:
            print(oid)

            await self.database.execute(
                "INSERT INTO tags (contentid, tag) VALUES (?, ?)",
                {"contentid": contentid, "tag": "invalid"},
            )
