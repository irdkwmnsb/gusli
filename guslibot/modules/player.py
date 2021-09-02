import json
from typing import Optional

import math
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
# noinspection PyTypeChecker
play_current_task = None  # type: AudioRequest
play_queue_lock = asyncio.Lock()
MUSIC_FOLDER = os.path.join(config.STORAGE_LOCATION, "music")
os.makedirs(MUSIC_FOLDER, exist_ok=True)
# noinspection PyTypeChecker
player = None  # type: vlc.MediaPlayer


async def get_loc_for_audio(audio: types.Audio):
    return os.path.join(MUSIC_FOLDER, pathvalidate.sanitize_filename(audio.file_unique_id))


class AudioRequest():
    by: int
    by_displayname: str
    by_username: Optional[str]
    mrl: str
    title: str
    filename: str
    orig_message: types.Message

    def __init__(self, by, by_displayname, mrl, title, orig_message, filename, by_username=None):
        self.by = by
        self.by_displayname = by_displayname
        self.mrl = mrl
        self.title = title
        self.by_username = by_username
        self.filename = filename
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
                      audio.file_name,
                      from_user.username
                      )
    logger.debug(rq.__dict__)
    # if not play_task or play_task.done():
    #     logger.info("Starting player because it was empty")
    #     await start_playing()
    async with play_queue_lock:
        await play_queue.put(rq)
        msg = f"{play_queue.qsize() - 1} songs before you"
        if play_current_task is None:
            msg = "will be played next"
        await message.reply(f"Added to queue, " + msg)


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
    player.set_pause(True)
    await message.answer("ok")


@dp.message_handler(commands=["play"])
@auth.requires_permission("player.queue.play")
async def skip(message: types.Message):
    logger.info("Trying to pause")
    player.set_pause(False)
    await message.answer("ok")


@dp.message_handler(commands=["stop"])
@auth.requires_permission("player.queue.stop")
async def skip(message: types.Message):
    logger.info("Trying to stop")
    play_queue._queue.clear()
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
    player.audio_set_volume(vol)
    if vol < 0 or vol > 100:
        await message.reply("Not in range [0; 100], proceed at own risk.")
    else:
        await message.answer("ok")


@dp.message_handler(commands=["volume_get"])
@auth.requires_permission("player.queue.volume.get")
async def skip(message: types.Message):
    vol = player.audio_get_volume()
    await message.answer(f"Player is at {vol}")


def format_request(song: AudioRequest):
    if song:
        return f"{song.title or song.filename} requested by {song.by_displayname}" + \
               f" (@ {song.by_username})" if song.by_username else ""
    else:
        return "Nothing is playing"


def format_time(time_ms):
    neg = time_ms < 0
    time_ms = abs(time_ms)
    secs = time_ms / 1000
    mins = secs / 60
    hours = mins / 60
    return ("-" if neg else "") + \
           (f"{int(hours)}:" if hours > 1 else "") + \
           f"{int(mins % 60):02}:{int(secs % 60):02}"


def make_bar(percent, length):
    cells = max(1, int(round(percent * length / 100)))
    return "#" * cells + "-" * (length - cells)


def get_player_string():
    emojis = {vlc.State.Ended: "🔚",
              vlc.State.Playing: "▶",
              vlc.State.Paused: "⏸",
              vlc.State.Buffering: "⌛",
              vlc.State.Opening: "📂",
              vlc.State.Error: "‼",
              vlc.State.NothingSpecial: "🤷🏻‍",
              vlc.State.Stopped: "⏹"}
    bar_lengh = 20
    emoji = emojis[player.get_state()]
    l = player.get_length()
    t = player.get_time()
    bar = make_bar(player.get_position() * 100, bar_lengh)
    return f"{emoji} {format_time(t)} {bar} {format_time(l)} ({format_time(l - t)})\n" + format_request(
        play_current_task)


@dp.message_handler(commands=["list", "queue"])
@auth.requires_permission("player.queue.list")
async def skip(message: types.Message):
    msg = ["Currently playing:",
           get_player_string(),
           "==============",
           "Current queue:"]
    # noinspection PyUnresolvedReferences
    q = play_queue._queue
    for i, song in enumerate(q):  # type: int, AudioRequest
        msg.append(f"{i + 1}. {format_request(song)}")
    if not q:
        msg.append("Nothing")
    await message.answer("\n".join(msg))


async def playing_task():
    global player
    global play_current_task
    player = vlc.MediaPlayer()  # type: vlc.MediaPlayer
    player_logger = logger.getChild("player")
    player_logger.info("Started player")
    while True:
        try:
            player_logger.info("Waiting for song")
            play_current_task = await play_queue.get()
            player_logger.info("Playing %s", play_current_task.title)
            player.set_mrl(play_current_task.mrl)
            result = player.play()
            # if not player.is_playing():
            #     await song.orig_message.reply("Could not start song")
            # else:
            #     logger.info("Successfully started")
            if result == -1:
                player_logger.error("Failed playing song")
                player_logger.debug(play_current_task)
                await play_current_task.orig_message.reply("Error playing that song:")
            while player.get_state() in [vlc.State.Opening, vlc.State.Buffering]:
                player_logger.info(f"Player is loading")
                await asyncio.sleep(0.2)
            while player.get_state() != vlc.State.Ended:
                player_logger.info(f"Player is playing")
                time_to_sleep = (player.get_length() - player.get_time()) / 1000
                player_logger.info(f"Sleeping %s seconds", time_to_sleep)
                await asyncio.sleep(time_to_sleep)
        except asyncio.CancelledError:
            player_logger.info("Got CancelledError, skipping song")
        finally:
            player.stop()
            play_current_task = None
            # if play_queue.empty():
            #     raise


async def start_playing():
    global play_task
    logger.info("Starting player")
    play_task = asyncio.create_task(playing_task())
