import os
import asyncio
import uuid
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup,
    KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from dotenv import load_dotenv

# === Загрузка токена из .env ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# === Настройка бота и диспетчера ===
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# === Машина состояний (FSM) ===
class ReminderFSM(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_text = State()
    editing_date = State()
    editing_time = State()
    editing_text = State()

# === Активные напоминания: user_id → список напоминаний ===
# Каждый элемент: {"id": ..., "text": ..., "time": ..., "task": ...}
active_reminders: dict[int, list[dict]] = {}

# === /start ===
@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привет!\n\nНапиши /remind, чтобы создать напоминание.\nНапиши /myreminders, чтобы посмотреть активные.")

# === /remind: начало создания напоминания ===
@dp.message(Command("remind"))
async def start_reminder(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Сегодня"), KeyboardButton(text="Завтра")],
        [KeyboardButton(text="Указать дату вручную")],
    ], resize_keyboard=True)
    await message.answer("📅 Выберите дату для напоминания:", reply_markup=kb)
    await state.set_state(ReminderFSM.waiting_for_date)

# === Обработка выбора даты ===
@dp.message(ReminderFSM.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    text = message.text.lower()
    if text == "сегодня":
        date = datetime.now().date()
    elif text == "завтра":
        date = (datetime.now() + timedelta(days=1)).date()
    elif text == "указать дату вручную":
        await message.answer("📆 Выберите дату:", reply_markup=await SimpleCalendar().start_calendar())
        return
    else:
        try:
            date = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            await message.answer("❌ Неверный формат. Введите дату ещё раз:")
            return

    await state.update_data(date=date)
    await message.answer("⏰ Введите время в формате ЧЧ:ММ:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ReminderFSM.waiting_for_time)

# === Обработка выбора даты из календаря ===
@dp.callback_query(SimpleCalendarCallback.filter())
async def calendar_handler(callback: CallbackQuery, callback_data: dict, state: FSMContext):
    current_state = await state.get_state()
    selected, date = await SimpleCalendar().process_selection(callback, callback_data)
    if selected:
        if current_state == ReminderFSM.editing_date.state:
            await state.update_data(new_date=date)
            await callback.message.answer(f"📅 Вы выбрали: {date.strftime('%d.%m.%Y')}")
            await callback.message.answer("⏰ Введите новое время в формате ЧЧ:ММ:")
            await state.set_state(ReminderFSM.editing_time)
        else:
            await state.update_data(date=date)
            await callback.message.answer(f"📅 Вы выбрали: {date.strftime('%d.%m.%Y')}")
            await callback.message.answer("⏰ Введите время в формате ЧЧ:ММ:")
            await state.set_state(ReminderFSM.waiting_for_time)

# === Обработка времени ===
@dp.message(ReminderFSM.waiting_for_time)
@dp.message(ReminderFSM.editing_time)
async def process_time(message: Message, state: FSMContext):
    try:
        time = datetime.strptime(message.text, "%H:%M").time()
    except ValueError:
        await message.answer("❌ Неверный формат. Введите время ЧЧ:ММ:")
        return

    current_state = await state.get_state()
    if current_state == ReminderFSM.editing_time.state:
        await state.update_data(new_time=time)
        await message.answer("📝 Введите новый текст напоминания:")
        await state.set_state(ReminderFSM.editing_text)
    else:
        await state.update_data(time=time)
        await message.answer("📝 Введите текст напоминания:")
        await state.set_state(ReminderFSM.waiting_for_text)

# === Обработка финального текста ===
@dp.message(ReminderFSM.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    data = await state.get_data()
    date, time = data["date"], data["time"]
    remind_at = datetime.combine(date, time)
    text = message.text
    if (delay := (remind_at - datetime.now()).total_seconds()) <= 0:
        await message.answer("❌ Указанное время уже прошло.")
        return

    reminder_id = str(uuid.uuid4())[:8]
    task = asyncio.create_task(send_reminder_after(delay, message.from_user.id, text, reminder_id))
    active_reminders.setdefault(message.from_user.id, []).append({
        "id": reminder_id,
        "task": task,
        "text": text,
        "time": remind_at
    })

    await message.answer(
        f"✅ Напоминание установлено на {remind_at.strftime('%d.%m.%Y %H:%M')}:\n{text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{reminder_id}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{reminder_id}")
            ]
        ])
    )
    await state.clear()

# === Задача напоминания ===
async def send_reminder_after(delay, user_id, text, reminder_id):
    try:
        await asyncio.sleep(delay)
        await bot.send_message(chat_id=user_id, text=f"🔔 Напоминание: {text}")
    except asyncio.CancelledError:
        await bot.send_message(chat_id=user_id, text="❌ Напоминание отменено.")
    finally:
        active_reminders[user_id] = [r for r in active_reminders.get(user_id, []) if r["id"] != reminder_id]

# === Отмена напоминания ===
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_reminder(callback: CallbackQuery):
    reminder_id = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    for r in active_reminders.get(user_id, []):
        if r["id"] == reminder_id:
            r["task"].cancel()
            await callback.answer("Напоминание отменено", show_alert=True)
            return
    await callback.answer("Не найдено", show_alert=True)

# === Редактирование напоминания ===
@dp.callback_query(F.data.startswith("edit_"))
async def edit_reminder(callback: CallbackQuery, state: FSMContext):
    reminder_id = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    for r in active_reminders.get(user_id, []):
        if r["id"] == reminder_id:
            await state.set_state(ReminderFSM.editing_date)
            await state.update_data(reminder_id=reminder_id)
            kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="Сегодня"), KeyboardButton(text="Завтра")],
                [KeyboardButton(text="Указать дату вручную")],
            ], resize_keyboard=True)
            await callback.message.answer("📅 Выберите новую дату:", reply_markup=kb)
            await callback.answer()
            return
    await callback.answer("Не найдено", show_alert=True)

@dp.message(ReminderFSM.editing_text)
async def finish_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    new_date, new_time = data["new_date"], data["new_time"]
    reminder_id = data["reminder_id"]
    new_dt = datetime.combine(new_date, new_time)
    if (delay := (new_dt - datetime.now()).total_seconds()) <= 0:
        await message.answer("❌ Время уже прошло.")
        return

    new_text = message.text
    user_id = message.from_user.id

    for i, r in enumerate(active_reminders.get(user_id, [])):
        if r["id"] == reminder_id:
            r["task"].cancel()
            task = asyncio.create_task(send_reminder_after(delay, user_id, new_text, reminder_id))
            active_reminders[user_id][i] = {
                "id": reminder_id,
                "task": task,
                "text": new_text,
                "time": new_dt
            }
            break

    await message.answer(f"✅ Напоминание обновлено на {new_dt.strftime('%d.%m.%Y %H:%M')}:\n{new_text}")
    await state.clear()

# === Список напоминаний ===
@dp.message(Command("myreminders"))
async def show_reminders(message: Message):
    reminders = active_reminders.get(message.from_user.id, [])
    if not reminders:
        await message.answer("У тебя нет активных напоминаний.")
        return
    for r in reminders:
        await message.answer(
            f"📌 {r['time'].strftime('%d.%m.%Y %H:%M')}\n📝 {r['text']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{r['id']}"),
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{r['id']}")
                ]
            ])
        )

# === Запуск ===
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
