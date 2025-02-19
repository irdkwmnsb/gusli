import asyncio
import traceback
import nest_asyncio
nest_asyncio.apply()


from aiogram.utils import executor
from aiogram.types import BotCommand

import guslibot.bot
import guslibot.log as log
import guslibot.player as player_module
from guslibot.web.app import start_server


async def rerun_on_exception(coro, *args, **kwargs):
    while True:
        try:
            await coro(*args, **kwargs)
        except guslibot.bot.asyncio.CancelledError:
            # don't interfere with cancellations
            raise
        except Exception:
            log.logger.exception("Caught exception in %r", coro)
        finally:
            log.logger.warning("Sleeping for 10 seconds")
            await guslibot.bot.asyncio.sleep(10)

async def setup_bot_commands(*args, **kwargs):
    bot_commands = [
        BotCommand(command="/skip", description="skip this audio"),
        BotCommand(command="/pause", description="pause")
        ,BotCommand(command="/play", description="play")
        ,BotCommand(command="/stop", description="stop")
        ,BotCommand(command="/loop_on", description="loop on")
        ,BotCommand(command="/loop_off", description="loop off")
        ,BotCommand(command="/volume_set", description="usage: /volume_set <number between 0 and 100>")
        ,BotCommand(command="/volume_get", description="get volume")
        ,BotCommand(command="/tts", description="text to speech. usage: /tts <text to say>")
        ,BotCommand(command="/download", description="download video from youtube. Usage: /download <link> of /download <name of video>")
        ,BotCommand(command="/playstream", description="play stream from youtube. Usage: /download <link> of /download <name of stream>")
        ,BotCommand(command="/list", description="list queue")
        ,BotCommand(command="/queue", description="same as /list")
        ,BotCommand(command="/q", description="same as /list")
        ,BotCommand(command="/grant_permission_user", description="admin only. Usage: /grant_permission_user +<perm> <user id>")
        ,BotCommand(command="/list_permission_user", description="admin only")
        ,BotCommand(command="/revoke_permission_user", description="admin only. Use same as for /grant_permission_user")
        ,BotCommand(command="/grant_permission_chat", description="admin only.")
        ,BotCommand(command="/list_permission_chat", description="admin only")
        ,BotCommand(command="/revoke_permission_chat", description="admin only")

    ]
    await guslibot.bot.bot.set_my_commands(bot_commands)

async def main():
    asyncio.create_task(start_server(), name="web-server")
    await player_module.start_player()
    log.logger.info(asyncio.all_tasks())
    executor.start_polling(guslibot.bot.dp, on_startup=setup_bot_commands)


if __name__ == "__main__":
    asyncio.run(main())
