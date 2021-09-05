import enum
import functools
from typing import Union

from aiogram import types
import guslibot.db as db
import guslibot.log as log
import inspect


# DEFAULT_PERMS = ["player"]
class ObjectReference(enum.Enum):
    user = db.users
    chat = db.chats


def match_permission(permission: str, to_test: str):
    return to_test.startswith(permission) or permission == "*"


async def has_permission(perm_list, permission: str):
    if not perm_list:
        return False
    can = False
    for perm in perm_list:  # type: str
        if len(perm) > 1:
            if match_permission(perm[1:], permission):
                can = perm[0] == "+"
        else:
            log.logger.error(f"Bad permission : {perm}")
    return can


async def fetch_perms(object_type: ObjectReference, id: int):
    obj = await object_type.value.find_one({"_id": id})
    if not obj:
        return []
    perm_list = obj["perm_list"]
    return perm_list


async def user_in_chat_has_permission(user_id: int, chat_id, permission: str):
    perms = await fetch_perms(ObjectReference.chat, chat_id) + await fetch_perms(ObjectReference.user, user_id)
    log.logger.debug(perms)
    return await has_permission(perms, permission)


async def user_has_permission(user_id: int, permission: str):
    return await has_permission(await fetch_perms(ObjectReference.user, user_id), permission)


async def chat_has_permission(chat_id: int, permission: str):
    return await has_permission(await fetch_perms(ObjectReference.chat, chat_id), permission)


def _check_spec(spec: inspect.FullArgSpec, kwargs: dict):
    return {k: v for k, v in kwargs.items() if k in set(spec.args + spec.kwonlyargs)}


def requires_permission(permission: str):
    def wrapper(callback):
        spec = inspect.getfullargspec(callback)

        async def handler(message: Union[types.Message, types.CallbackQuery], *args, **kwargs):
            if not await user_in_chat_has_permission(message.from_user.id, message.chat.id, permission):
                err_string = "You don't have permissions to " + permission
                if isinstance(message, types.Message):
                    await message.reply(err_string)
                if isinstance(message, types.CallbackQuery):
                    await message.answer(err_string)
            else:
                await callback(message, *args, **_check_spec(spec, kwargs))

        return handler

    return wrapper


requires_admin = requires_permission("admin")
requires_player = requires_permission("player")
