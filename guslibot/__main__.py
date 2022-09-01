import asyncio
import traceback
import nest_asyncio
nest_asyncio.apply()


from aiogram.utils import executor

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


async def main():
    asyncio.create_task(start_server(), name="web-server")
    await player_module.start_player()
    log.logger.info(asyncio.all_tasks())
    executor.start_polling(guslibot.bot.dp, on_startup=[])


if __name__ == "__main__":
    asyncio.run(main())
