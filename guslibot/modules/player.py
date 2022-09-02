import pathlib
import tempfile

from aiogram import types
from aiogram.types import ContentType

import guslibot.auth as auth
import guslibot.player
from guslibot.bot import dp
from guslibot.log import logger
import asyncio.queues
import os
import vlc
import httpx
import hashlib
import textwrap

# import magic
from guslibot.player import *


async def get_loc_for_media(file: Union[types.Audio, types.Voice, types.Video]):
    return os.path.join(MUSIC_FOLDER, pathvalidate.sanitize_filename(file.file_unique_id))


# class AudioRequest():
#     by: int
#     by_displayname: str
#     by_username: Optional[str]
#     mrl: str
#     title: str
#     filename: str
#     orig_message: types.Message
#
#     def __init__(self, by, by_displayname, mrl, title, orig_message, filename, by_username=None):
#         self.by = by
#         self.by_displayname = by_displayname
#         self.mrl = mrl
#         self.title = title
#         self.by_username = by_username
#         self.filename = filename
#         self.orig_message = orig_message

@dp.message_handler(content_types=[ContentType.AUDIO, ContentType.VIDEO, ContentType.VOICE])
@auth.requires_permission("player.queue.add")
async def enqueue(message: types.Message):
    logger.debug("Audio request")
    audio = message.audio or message.voice or message.video
    loc = await get_loc_for_media(audio)
    msg_obj = None
    if os.path.isfile(loc):
        logger.debug("Already saved")
    else:
        logger.debug("Saving @ %s", loc)
        msg_obj = await message.reply("Downloading...")
        await audio.download(loc)
        logger.debug("Downloaded %s", loc)
    from_user = message.from_user
    rq = TelegramAudioRequest(by_id=from_user.id,
                              by_displayname=from_user.first_name + " " + (from_user.last_name or ""),
                              mrl=loc,
                              title=getattr(audio, "title", "Без названия"),
                              orig_message=message,
                              filename=getattr(audio, "first_name", "Без файла"),
                              by_username=from_user.username
                              )
    logger.debug(rq.__dict__)
    # if not play_task or play_task.done():
    #     logger.info("Starting player because it was empty")
    #     await start_playing()
    new_size = await pl_add(rq)
    msg_str = f"{new_size} songs before you"
    if play_current_task is None:
        msg_str = "will be played next"
    msg_str = f"Added to queue, " + msg_str
    if msg_obj:
        await msg_obj.edit_text(msg_str)
    else:
        await message.reply(msg_str)


@dp.message_handler(commands=["skip"])
@auth.requires_permission("player.queue.skip")
async def skip(message: types.Message):
    logger.info("Trying to skip")
    await pl_skip()
    await message.answer("ok")


@dp.message_handler(commands=["pause"])
@auth.requires_permission("player.queue.pause")
async def pause(message: types.Message):
    logger.info("Trying to pause")
    await pl_pause()
    await message.answer("ok")


@dp.message_handler(commands=["play"])
@auth.requires_permission("player.queue.play")
async def play(message: types.Message):
    logger.info("Trying to pause")
    await pl_play()
    await message.answer("ok")


@dp.message_handler(commands=["stop"])
@auth.requires_permission("player.queue.stop")
async def stop(message: types.Message):
    logger.info("Trying to stop")
    await pl_stop()
    await message.answer("ok")


async def set_loop(new_val: bool):
    await pl_set_loop(new_val)
    logger.info("loop=%s", guslibot.player.play_is_looped)


@dp.message_handler(commands=["loop_on"])
@auth.requires_permission("player.queue.loop.on")
async def loop_on(message: types.Message):
    await set_loop(True)
    await message.answer("ok")


@dp.message_handler(commands=["loop_off"])
@auth.requires_permission("player.queue.loop.off")
async def loop_off(message: types.Message):
    await set_loop(False)
    await message.answer("ok")


async def set_volume(vol):
    await pl_set_volume(vol)


@dp.message_handler(commands=["volume_set"])
@auth.requires_permission("player.volume.set")
async def volume_set(message: types.Message):
    arg = message.text.split()
    if len(arg) < 2:
        await message.reply("Must specify arg")
    vol = arg[1]
    if not vol.isnumeric():
        await message.reply("Incorrect arg")
    vol = int(vol)
    if (vol < 0 or vol > 100) and not await auth.user_in_chat_has_permission(message.from_user.id,
                                                                             message.chat.id,
                                                                             "player.volume.set.extreme"):
        await message.reply("You are not allowed to set the volume out of range [0; 100]")
        return
    await set_volume(vol)
    if vol < 0 or vol > 100:
        await message.reply("Not in range [0; 100], proceed at own risk.")
    else:
        await message.answer("ok")


@dp.message_handler(commands=["volume_get"])
@auth.requires_permission("player.volume.get")
async def volume_get(message: types.Message):
    await message.answer(f"Player is at {play_set_volume}")


def get_loc_for_tts(text: str):
    filename = hashlib.md5(text.encode()).hexdigest()
    return pathlib.Path(MUSIC_FOLDER, filename + ".mp3")


@dp.message_handler(commands=["tts"])
@auth.requires_permission("player.tts")
async def tts(message: types.Message):
    msg = await message.reply("Working...")
    text = message.get_args()
    loc = get_loc_for_tts(text)
    logger.debug(loc)
    if not loc.exists():
        await msg.edit_text("Downloading...")
        async with httpx.AsyncClient() as client:
            r = await client.post("https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize", data={
                "text": text,
                "format": "mp3"
            }, headers={
                "Authorization": "Api-Key AQVN29zZnajTeidJjAFBEdCoOaoc7clOGaKtzKpU"
            })
            logger.debug(r.status_code)
            with open(loc, "wb") as download_file:
                logger.debug("Opened")
                logger.debug("Reading")
                for chunk in r.iter_bytes():
                    download_file.write(chunk)
                    logger.debug("Putting")
            await msg.edit_text("Downloaded...")
    from_user = message.from_user
    rq = TelegramAudioRequest(by_id=from_user.id,
                              by_displayname=from_user.first_name + " " + (from_user.last_name or ""),
                              mrl=loc,
                              title=textwrap.shorten(text, placeholder=" ...", width=30),
                              orig_message=message,
                              filename="tts.mp3",
                              by_username=from_user.username)
    await pl_add(rq)
    await msg.edit_text("Added...")


@dp.message_handler(commands=["list", "queue", "q"])
@auth.requires_permission("player.queue.list")
async def skip(message: types.Message):
    msg = ["Currently playing:",
           pl_get_player_string(),
           "==============",
           "Current queue:"]
    # noinspection PyUnresolvedReferences
    q = await pl_get_queue()
    for i, song in enumerate(q):  # type: int, AudioRequest
        msg.append(f"{i + 1}. {format_request(song)}")
    if not q:
        msg.append("Nothing")
    await message.answer("\n".join(msg))
