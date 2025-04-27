import asyncio
from trader_bot import TraderBot
from telegram_bot import run_telegram_bot

async def main():
    bot = TraderBot()
    await bot.start()

    # Telegram botni start qilamiz
    await run_telegram_bot(bot)

if __name__ == "__main__":
    asyncio.run(main())
