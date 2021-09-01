import json
from typing import Optional, Callable

from aiogram import types
from aiogram import md
from aiogram.types import ContentType

import guslibot.db as db
import guslibot.auth as auth
from guslibot.bot import dp, bot
from guslibot.log import logger
import guslibot.config as config
from collections import deque
import asyncio.queues
import os
import pathvalidate
import vlc
import traceback
# import magic
import mimetypes


async def extract_int(arg, on_error: Callable):
    if arg.isnumeric():
        return int(arg)
    else:
        await on_error()


@dp.message_handler(commands=["grant_permission_user"])
@auth.requires_permission("admin.permissions.user.grant")
async def grant_user(message: types.Message):
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user.id
    expl = message.text.split()
    if len(expl) < 2:
        await message.reply("Must specify permission to grant.")
    permission = expl[1]
    if len(expl) > 2:
        target = await extract_int(expl[2], lambda: message.reply("Incorrect user id"))
    if not target:
        await message.reply("Must specify user. Reply to message or specify user id")
    await db.users.update_one({"_id": target}, {"$addToSet": {"perm_list": permission}}, upsert=True)
    await message.reply(f"Granted user {target} permission to {permission}")


@dp.message_handler(commands=["list_permission_user"])
@auth.requires_permission("admin.permissions.user.list")
async def list_user(message: types.Message):
    target = message.from_user.id
    if message.reply_to_message:
        target = message.reply_to_message.from_user.id
    expl = message.text.split()
    if len(expl) > 2:
        target = await extract_int(expl[2], lambda: message.reply("Incorrect user id"))
    if not target:
        await message.reply("Must specify user. Reply to message or specify user id")
    d = await db.users.find_one({"_id": target}) or {"perm_list": []}
    await message.reply(f"User {target} has permissions to:\n" + "\n".join(d["perm_list"]))


@dp.message_handler(commands=["revoke_permission_user"])
@auth.requires_permission("admin.permissions.user.revoke")
async def revoke_user(message: types.Message):
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user.id
    expl = message.text.split()
    if len(expl) < 2:
        await message.reply("Must specify permission to revoke.")
    permission = expl[1]
    if len(expl) > 2:
        target = await extract_int(expl[2], lambda: message.reply("Incorrect user id"))
    if not target:
        await message.reply("Must specify user. Reply to message or specify user id")
    await db.users.update_one({"_id": target}, {"$pull": {"perm_list": permission}}, upsert=True)
    await message.reply(f"Revoked user {target} permission to {permission}")


@dp.message_handler(commands=["grant_permission_chat"])
@auth.requires_permission("admin.permissions.chat.grant")
async def grant_chat(message: types.Message):
    target = message.chat.id
    expl = message.text.split()
    if len(expl) < 2:
        await message.reply("Must specify permission to grant.")
    permission = expl[1]
    await db.chats.update_one({"_id": target}, {"$addToSet": {"perm_list": permission}}, upsert=True)
    await message.reply(f"Granted chat {target} permission to {permission}")


@dp.message_handler(commands=["list_permission_chat"])
@auth.requires_permission("admin.permissions.chat.list")
async def list_user(message: types.Message):
    target = message.chat.id
    expl = message.text.split()
    if len(expl) > 2:
        target = await extract_int(expl[2], lambda: message.reply("Incorrect chat id"))
    d = await db.chats.find_one({"_id": target}) or {"perm_list": []}
    await message.reply(f"Chat {target} has permissions to:\n" + "\n".join(d["perm_list"]))


@dp.message_handler(commands=["revoke_permission_chat"])
@auth.requires_permission("admin.permissions.chat.revoke")
async def revoke_chat(message: types.Message):
    target = message.chat.id
    expl = message.text.split()
    if len(expl) < 2:
        await message.reply("Must specify permission to revoke.")
    permission = expl[1]
    if len(expl) > 2:
        target = await extract_int(expl[2], lambda: message.reply("Incorrect chat id"))
    await db.chats.update_one({"_id": target}, {"$pull": {"perm_list": permission}}, upsert=True)
    await message.reply(f"Revoked chat {target} permission to {permission}")
