from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
import asyncio
import os

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет! Напиши /remind [текст] — я напомню через 5 минут.")

@dp.message(Command("remind"))
async def remind_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Формат: /remind [текст]")
        return
    text = args[1]
    await message.answer(f"Окей, напомню через 5 минут: \"{text}\"")
    await asyncio.sleep(300)
    await message.answer(f"Напоминание: {text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
