import asyncio
import base64
import json
import random
from typing import Any, Union

import orjson
from pydantic import BaseModel
from starlette.responses import Response

from immersive_library.common import database
from immersive_library.models import ContentUpload
from immersive_library.routers.content import add_content, get_content, update_content
from immersive_library.routers.deprecated.content import list_content
from immersive_library.routers.deprecated.user import get_user
from immersive_library.routers.like import add_like, delete_like
from immersive_library.routers.tag import (
    add_tag,
    delete_tag,
    list_project_tags,
    list_content_tags,
)
from immersive_library.routers.tools import run_post_upload_callbacks
from immersive_library.routers.user import get_users, set_user
from immersive_library.utils import token_to_userid, set_moderator, login_user


def print_json(param: Any):
    if isinstance(param, Response):
        print(bytes(param.body).decode())
    elif isinstance(param, dict):
        print(json.dumps(param))
    else:
        print(param.model_dump_json())


def decode(r: Union[BaseModel, Response]) -> dict:
    if isinstance(r, Response):
        return orjson.loads(r.body)
    else:
        return r.model_dump()


async def catch(func, *args, **kwargs) -> Any:
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        return {"message": str(e)}


async def run_tests():
    token = "guest_token"

    await login_user(database, "123", "Warp", token)

    # Insert test
    contentid = decode(
        await add_content(
            "test",
            ContentUpload(
                title="Test object",
                meta="{}",
                data=base64.b64encode(str(random.random()).encode()).decode(),
            ),
            token,
        )
    )["contentid"]
    print(f"Data inserted with oid {contentid}")

    # Get test
    print_json(await catch(get_content, "test", contentid))

    # Get list test
    print_json(await catch(list_content, "test"))

    # Rename test
    print_json(
        await update_content(
            "test",
            contentid,
            ContentUpload(
                title="Test renamed object",
                meta="{}",
                data=base64.b64encode(str(random.random()).encode()).decode(),
            ),
            token,
        )
    )
    print_json(await catch(get_content, "test", contentid))

    # Like
    print_json(await catch(add_like, "test", contentid, token))
    print_json(await catch(add_like, "test2", contentid, token))
    print_json(await catch(get_content, "test", contentid))
    print_json(await catch(add_like, "test", contentid, token))

    # Delete like
    print_json(await catch(delete_like, "test", contentid, token))
    print_json(await catch(get_content, "test", contentid))
    print_json(await catch(delete_like, "test", contentid, token))

    # Tag
    print_json(await catch(add_tag, "test", contentid, "Tag1", token))
    print_json(await catch(add_tag, "test", contentid, "Tag2", token))
    print_json(await catch(get_content, "test", contentid))
    print_json(await catch(add_tag, "test", contentid, "Tag2", token))

    # Untag
    print_json(await catch(delete_tag, "test", contentid, "Tag1", token))
    print_json(await catch(get_content, "test", contentid))
    print_json(await catch(delete_tag, "test", contentid, "Tag1", token))

    # User
    print_json(await catch(get_users, "test"))
    print_json(await catch(get_user, "test", 1))

    # Tags
    print_json(await catch(list_project_tags, "test"))
    print_json(await catch(list_content_tags, "test", contentid))

    # Moderator tools
    print_json(await catch(set_user, 1, token, moderator=True))

    # Make moderator
    userid = await token_to_userid(database, token)
    assert userid is not None
    await set_moderator(database, userid, True)

    print_json(await catch(set_user, userid, token, moderator=True))
    print_json(await catch(set_user, userid, token, banned=True))
    print_json(await catch(set_user, userid, token, purge=True))

    print_json(await catch(run_post_upload_callbacks, "test", token))


asyncio.run(run_tests())
