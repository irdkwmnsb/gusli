import json
from typing import Optional

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

play_queue = asyncio.queues.Queue()  # type: asyncio.queues.Queue[AudioRequest]
# noinspection PyTypeChecker
play_task = None  # type: asyncio.Task
play_queue_lock = asyncio.Lock()
MUSIC_FOLDER = os.path.join(config.STORAGE_LOCATION, "music")
os.makedirs(MUSIC_FOLDER, exist_ok=True)
player = None  # type: vlc.MediaPlayer


async def get_loc_for_audio(audio: types.Audio):
    return os.path.join(MUSIC_FOLDER, pathvalidate.sanitize_filename(audio.file_unique_id))


class AudioRequest():
    by: int
    by_displayname: str
    by_username: Optional[str]
    mrl: str
    title: str
    orig_message: types.Message

    def __init__(self, by, by_displayname, mrl, title, orig_message, by_username=None):
        self.by = by
        self.by_displayname = by_displayname
        self.mrl = mrl
        self.title = title
        self.by_username = by_username
        self.orig_message = orig_message


@dp.message_handler(content_types=ContentType.AUDIO)
@auth.requires_permission("player.queue.add")
async def enqueue(message: types.Message):
    logger.debug("Audio request")
    audio = message.audio
    loc = await get_loc_for_audio(audio)
    if os.path.isfile(loc):
        logger.debug("Already saved")
    else:
        logger.debug("Saving @ %s", loc)
        await audio.download(loc)
        logger.debug("Downloaded %s", loc)
    from_user = message.from_user
    rq = AudioRequest(from_user.id,
                      from_user.first_name + " " + (from_user.last_name or ""),
                      loc,
                      audio.title,
                      message,
                      from_user.username
                      )
    logger.debug(rq.__dict__)
    # if not play_task or play_task.done():
    #     logger.info("Starting player because it was empty")
    #     await start_playing()
    async with play_queue_lock:
        await play_queue.put(rq)
        await message.reply(f"Added to queue, {play_queue.qsize() - 1} songs before you")


@dp.message_handler(commands=["skip"])
@auth.requires_permission("player.queue.skip")
async def skip(message: types.Message):
    logger.info("Trying to skip")
    play_task.cancel()
    await message.answer("ok")


@dp.message_handler(commands=["pause"])
@auth.requires_permission("player.queue.pause")
async def skip(message: types.Message):
    logger.info("Trying to pause")
    player.pause()
    await message.answer("ok")


@dp.message_handler(commands=["stop"])
@auth.requires_permission("player.queue.stop")
async def skip(message: types.Message):
    logger.info("Trying to stop")
    play_queue.empty()
    play_task.cancel()
    await message.answer("ok")


@dp.message_handler(commands=["volume_set"])
@auth.requires_permission("player.queue.volume.set")
async def skip(message: types.Message):
    arg = message.text.split()
    if len(arg) < 2:
        await message.reply("Must specify arg")
    vol = arg[1]
    if not vol.isnumeric():
        await message.reply("Incorrect arg")
    vol = int(vol)
    if vol < 0 or vol > 100:
        await message.reply("Not in range [0; 100]")
    player.audio_set_volume(vol)
    await message.answer("ok")


@dp.message_handler(commands=["volume_get"])
@auth.requires_permission("player.queue.volume.get")
async def skip(message: types.Message):
    vol = player.audio_get_volume()
    await message.answer(f"Player is at {vol}")


@dp.message_handler(commands=["list", "queue"])
@auth.requires_permission("player.queue.list")
async def skip(message: types.Message):
    msg = ["Current queue:"]
    # noinspection PyUnresolvedReferences
    q = play_queue._queue
    for i, song in enumerate(q):  # type: int, AudioRequest
        msg.append(f"{i + 1}. {song.title} requested by {song.by_displayname}" +
                   (f" (@ {song.by_username})" if song.by_username else ""))
    if not q:
        msg.append("empty")
    await message.answer("\n".join(msg))


async def playing_task():
    global player
    player = vlc.MediaPlayer()  # type: vlc.MediaPlayer
    player_logger = logger.getChild("player")
    player_logger.info("Started player")
    while True:
        try:
            player_logger.info("Waiting for song")
            song = await play_queue.get()
            player_logger.info("Playing %s", song.title)
            try:
                player.set_mrl(song.mrl)
                player.play()
                # if not player.is_playing():
                #     await song.orig_message.reply("Could not start song")
                # else:
                #     logger.info("Successfully started")
            except Exception:
                player_logger.exception("Failed playing song")
                await song.orig_message.reply("Error playing that song:")
                traceback.format_exc()
                continue
            await asyncio.sleep(0.2)
            while player.get_media() != -1:
                player_logger.info(f"Player is playing")
                time_to_sleep = (player.get_length() - player.get_time()) / 1000
                if time_to_sleep < 0.2:
                    break
                player_logger.info(f"Sleeping %s seconds", time_to_sleep)
                await asyncio.sleep(time_to_sleep)
        except asyncio.CancelledError:
            player_logger.info("Got CancelledError, skipping song")
            player.stop()
            # if play_queue.empty():
            #     raise


async def start_playing():
    global play_task
    logger.info("Starting player")
    play_task = asyncio.create_task(playing_task())
