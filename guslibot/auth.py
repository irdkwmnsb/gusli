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
    chats = db.chats


async def has_permission(object_type: ObjectReference, id, permission: str):
    obj = await object_type.value.find_one({"_id": id})
    if not obj:
        return False
    perm_list = obj["perm_list"]
    log.logger.debug(perm_list)
    if not perm_list:
        return False
    for perm in perm_list:
        if permission.startswith(perm) or perm == "*":
            return True


async def user_has_permission(user_id: int, permission: str):
    return await has_permission(ObjectReference.user, user_id, permission)


async def chat_has_permission(chat_id: int, permission: str):
    return await has_permission(ObjectReference.chats, chat_id, permission)


def _check_spec(spec: inspect.FullArgSpec, kwargs: dict):
    return {k: v for k, v in kwargs.items() if k in set(spec.args + spec.kwonlyargs)}


def requires_permission(permission: str):
    def wrapper(callback):
        spec = inspect.getfullargspec(callback)

        async def handler(message: Union[types.Message, types.CallbackQuery], *args, **kwargs):
            if not (await user_has_permission(message.from_user.id, permission) or
                    await chat_has_permission(message.chat.id, permission)):
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
