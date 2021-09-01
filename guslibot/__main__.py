import asyncio
import traceback

from aiogram.utils import executor

import guslibot.bot
import guslibot.log as log
import guslibot.modules.player as player_module


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


if __name__ == "__main__":
    loop = guslibot.bot.asyncio.get_event_loop()

    loop.run_until_complete(player_module.start_playing())

    executor.start_polling(guslibot.bot.dp, on_startup=[], loop=loop)

