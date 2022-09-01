import asyncio.queues
import os
from typing import Union, Optional

import pathvalidate
import pydantic
import vlc
from aiogram import types

from guslibot import config as config

from guslibot.log import logger

play_queue = asyncio.queues.Queue()  # type: asyncio.queues.Queue[AudioRequest]
play_task = None  # type: asyncio.Task
play_current_task = None  # type: AudioRequest
play_queue_lock = asyncio.Lock()
play_is_looped = False
play_set_volume = 100
MUSIC_FOLDER = os.path.join(config.STORAGE_LOCATION, "music")
player = None  # type: vlc.MediaPlayer
os.makedirs(MUSIC_FOLDER, exist_ok=True)


async def get_loc_for_media(file: Union[types.Audio, types.Voice, types.Video]):
    return os.path.join(MUSIC_FOLDER, pathvalidate.sanitize_filename(file.file_unique_id))


class AudioRequest(pydantic.BaseModel):
    by_displayname: str
    mrl: str
    title: str
    filename: str


class TelegramAudioRequest(AudioRequest):
    by_id: int
    orig_message: types.Message
    by_username: Optional[str]

    class Config:
        arbitrary_types_allowed = True


async def pl_add(request: AudioRequest) -> int:
    async with play_queue_lock:
        await play_queue.put(request)
        return play_queue.qsize()


async def pl_skip():
    play_task.cancel()


async def pl_pause():
    player.set_pause(True)


async def pl_play():
    player.set_pause(False)


async def pl_stop():
    global play_is_looped
    play_queue._queue.clear()
    play_task.cancel()
    play_is_looped = False


async def pl_set_loop(new_val):
    global play_is_looped
    play_is_looped = new_val


async def pl_set_volume(new_vol):
    global play_set_volume
    play_set_volume = new_vol
    player.audio_set_volume(new_vol)


async def pl_get_queue():
    return play_queue._queue


async def playing_task():
    global player
    global play_current_task
    global play_set_volume
    global play_is_looped
    player = vlc.MediaPlayer()  # type: vlc.MediaPlayer
    player_logger = logger.getChild("player")
    player_logger.info("Started player")
    # player_logger.debug(repr(player))
    while True:
        try:
            player_logger.info("Waiting for song")
            play_current_task = await play_queue.get()
            logger.debug("current_task=%s", play_current_task)
            player_logger.info("Playing %s", play_current_task.title)
            if isinstance(play_current_task, TelegramAudioRequest):
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


def format_time(time_ms):
    neg = time_ms < 0
    time_ms = abs(time_ms)
    secs = time_ms / 1000
    mins = secs / 60
    hours = mins / 60
    return ("-" if neg else "") + \
           (f"{int(hours)}:" if hours > 1 else "") + \
           f"{int(mins % 60):02}:{int(secs % 60):02}"


def format_request(song: AudioRequest):
    if song:
        return f"{song.title or song.filename} requested by {song.by_displayname}" + \
               (f" (@ {song.by_username})" if isinstance(song, TelegramAudioRequest) and song.by_username else "")
    else:
        return "Nothing is playing"


def make_bar(percent, length):
    cells = max(1, int(round(percent * length / 100)))
    return "#" * cells + "-" * (length - cells)


def pl_get_player_string():
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
    return f"{emoji}{' 🔁' if play_is_looped else ''} {format_time(t)} {bar} {format_time(l)} ({format_time(t - l)})\n" \
           + format_request(play_current_task)


async def start_player(loop):
    global play_task
    logger.info("Starting player")
    play_task = asyncio.create_task(playing_task())
