import asyncio
import io

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types.mixins import Downloadable
import guslibot.config as config
import guslibot.db as db
import guslibot.log as log

bot = Bot(token=config.API_TOKEN)
Bot.set_current(bot)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


async def download_downloadable(file: Downloadable) -> bytes:
    b = io.BytesIO()
    await file.download(destination=b)
    return b.read()


import guslibot.modules.player
import guslibot.modules.admin
