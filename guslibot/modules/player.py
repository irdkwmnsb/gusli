import json
from typing import Optional, Union

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
play_is_looped = False
play_set_volume = 100
MUSIC_FOLDER = os.path.join(config.STORAGE_LOCATION, "music")
os.makedirs(MUSIC_FOLDER, exist_ok=True)
# noinspection PyTypeChecker
player = None  # type: vlc.MediaPlayer


async def get_loc_for_media(file: Union[types.Audio, types.Voice, types.Video]):
    return os.path.join(MUSIC_FOLDER, pathvalidate.sanitize_filename(file.file_unique_id))


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
    rq = AudioRequest(from_user.id,
                      from_user.first_name + " " + (from_user.last_name or ""),
                      loc,
                      getattr(audio, "title", "Без названия"),
                      message,
                      getattr(audio, "first_name", "Без файла"),
                      from_user.username
                      )
    logger.debug(rq.__dict__)
    # if not play_task or play_task.done():
    #     logger.info("Starting player because it was empty")
    #     await start_playing()
    async with play_queue_lock:
        await play_queue.put(rq)
        msg_str = f"{play_queue.qsize() - 1} songs before you"
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
    play_task.cancel()
    await message.answer("ok")


@dp.message_handler(commands=["pause"])
@auth.requires_permission("player.queue.pause")
async def pause(message: types.Message):
    logger.info("Trying to pause")
    player.set_pause(True)
    await message.answer("ok")


@dp.message_handler(commands=["play"])
@auth.requires_permission("player.queue.play")
async def play(message: types.Message):
    logger.info("Trying to pause")
    player.set_pause(False)
    await message.answer("ok")


@dp.message_handler(commands=["stop"])
@auth.requires_permission("player.queue.stop")
async def stop(message: types.Message):
    logger.info("Trying to stop")
    play_queue._queue.clear()
    play_task.cancel()
    global play_is_looped
    play_is_looped = False
    await message.answer("ok")


def set_loop(new_val: bool):
    global play_is_looped
    play_is_looped = new_val
    logger.info("loop=%s", play_is_looped)


@dp.message_handler(commands=["loop_on"])
@auth.requires_permission("player.queue.loop.on")
async def loop_on(message: types.Message):
    set_loop(True)
    await message.answer("ok")


@dp.message_handler(commands=["loop_off"])
@auth.requires_permission("player.queue.loop.off")
async def loop_off(message: types.Message):
    set_loop(False)
    await message.answer("ok")


def set_volume(vol):
    global play_set_volume
    play_set_volume = vol
    player.audio_set_volume(vol)


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
    set_volume(vol)
    if vol < 0 or vol > 100:
        await message.reply("Not in range [0; 100], proceed at own risk.")
    else:
        await message.answer("ok")


@dp.message_handler(commands=["volume_get"])
@auth.requires_permission("player.volume.get")
async def volume_get(message: types.Message):
    await message.answer(f"Player is at {play_set_volume}")


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
    return f"{emoji}{' 🔁' if play_is_looped else ''} {format_time(t)} {bar} {format_time(l)} ({format_time(t - l)})\n" + format_request(
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
    global play_set_volume
    global play_is_looped
    player = vlc.MediaPlayer()  # type: vlc.MediaPlayer
    player_logger = logger.getChild("player")
    player_logger.info("Started player")
    while True:
        try:
            logger.debug("current_task=%s", play_current_task)
            player_logger.info("Waiting for song")
            play_current_task = await play_queue.get()
            player_logger.info("Playing %s", play_current_task.title)
            await play_current_task.orig_message.reply("Playing now...")
            while True:
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
                    player_logger.info("Player is playing (at %s percent)", play_set_volume)
                    player.audio_set_volume(play_set_volume)
                    time_to_sleep = (player.get_length() - player.get_time()) / 1000
                    player_logger.info(f"Sleeping %s seconds", time_to_sleep)
                    await asyncio.sleep(time_to_sleep)
                if not play_is_looped:
                    break
                player_logger.info("Playing again")
        except asyncio.CancelledError:
            player_logger.info("Got CancelledError, skipping song")
        except Exception:
            player_logger.exception("Exception in player")
        finally:
            player_logger.debug("Stopping")
            player.stop()
            play_current_task = None
            # if play_queue.empty():
            #     raise


async def start_playing():
    global play_task
    logger.info("Starting player")
    play_task = asyncio.create_task(playing_task())
