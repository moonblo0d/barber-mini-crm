"""Telegram-бот: приймає заявки від клієнтів і сповіщає адміністратора."""
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from config import ADMIN_CHAT_ID, BUSINESS_NAME, SERVICES, STATUSES

log = logging.getLogger(__name__)
router = Router()

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{9,18}$")
BTN_NEW_LEAD = "✂️ Записатися"
BTN_CANCEL = "Скасувати"


class LeadForm(StatesGroup):
    name = State()
    service = State()
    phone = State()
    preferred_time = State()


# ---------- Клавіатури ----------

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_NEW_LEAD)]], resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def services_kb():
    kb = InlineKeyboardBuilder()
    for i, service in enumerate(SERVICES):
        kb.button(text=service, callback_data=f"svc:{i}")
    kb.adjust(1)
    return kb.as_markup()


def status_kb(lead_id: int):
    kb = InlineKeyboardBuilder()
    for key, label in STATUSES.items():
        if key != "new":
            kb.button(text=label, callback_data=f"st:{lead_id}:{key}")
    kb.adjust(3)
    return kb.as_markup()


# ---------- Форматування ----------

def format_lead(lead: dict) -> str:
    source = "Telegram" if lead["source"] == "telegram" else "Сайт"
    lines = [
        f"<b>Заявка #{lead['id']}</b> · {STATUSES.get(lead['status'], lead['status'])}",
        f"👤 {escape(lead['name'])}",
        f"📞 {escape(lead['phone'])}",
        f"✂️ {escape(lead['service'])}",
    ]
    if lead.get("preferred_time"):
        lines.append(f"🕒 {escape(lead['preferred_time'])}")
    if lead.get("comment"):
        lines.append(f"💬 {escape(lead['comment'])}")
    if lead.get("tg_username"):
        lines.append(f"✈️ @{escape(lead['tg_username'])}")
    lines.append(f"📍 Джерело: {source} · {lead['created_at'].replace('T', ' ')}")
    return "\n".join(lines)


async def notify_admin(bot: Bot, lead: dict) -> None:
    """Надсилає адміністратору картку нової заявки з кнопками статусу."""
    if not ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID не задано — сповіщення не надіслано (заявка #%s)", lead["id"])
        return
    try:
        await bot.send_message(ADMIN_CHAT_ID, "🔔 " + format_lead(lead), reply_markup=status_kb(lead["id"]))
    except Exception:  # мережа, неправильний chat id тощо — заявка вже збережена
        log.exception("Не вдалося надіслати сповіщення адміну")


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_CHAT_ID) and user_id == ADMIN_CHAT_ID


# ---------- Клієнтська частина ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"Привіт! Це бот <b>{escape(BUSINESS_NAME)}</b> 💈\n"
        "Тут можна записатися на стрижку за хвилину — без дзвінків.",
        reply_markup=main_menu(),
    )
    if is_admin(message.from_user.id):
        await message.answer("Команди адміна: /leads — останні заявки, /stats — статистика.")


@router.message(F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Скасовано. Коли будете готові — натисніть «Записатися».", reply_markup=main_menu())


@router.message(F.text == BTN_NEW_LEAD)
async def lead_start(message: Message, state: FSMContext) -> None:
    await state.set_state(LeadForm.name)
    await message.answer("Як до вас звертатися?", reply_markup=cancel_kb())


@router.message(LeadForm.name, F.text)
async def lead_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not 2 <= len(name) <= 60:
        await message.answer("Напишіть, будь ласка, ім'я (2–60 символів).")
        return
    await state.update_data(name=name)
    await state.set_state(LeadForm.service)
    await message.answer(f"Приємно, {escape(name)}! Оберіть послугу:", reply_markup=services_kb())


@router.callback_query(LeadForm.service, F.data.startswith("svc:"))
async def lead_service(call: CallbackQuery, state: FSMContext) -> None:
    index = int(call.data.split(":")[1])
    service = SERVICES[index]
    await state.update_data(service=service)
    await state.set_state(LeadForm.phone)
    await call.message.edit_text(f"Послуга: <b>{escape(service)}</b>")
    await call.message.answer("Залиште номер телефону — кнопкою нижче або текстом:", reply_markup=phone_kb())
    await call.answer()


@router.message(LeadForm.phone, F.contact)
async def lead_phone_contact(message: Message, state: FSMContext) -> None:
    await _save_phone(message, state, message.contact.phone_number)


@router.message(LeadForm.phone, F.text)
async def lead_phone_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        await message.answer("Схоже, це не номер. Приклад: +380 50 123 45 67")
        return
    await _save_phone(message, state, phone)


async def _save_phone(message: Message, state: FSMContext, phone: str) -> None:
    await state.update_data(phone=phone)
    await state.set_state(LeadForm.preferred_time)
    await message.answer(
        "Коли вам зручно прийти? Напишіть день і час (наприклад: «завтра після 18:00»).",
        reply_markup=cancel_kb(),
    )


@router.message(LeadForm.preferred_time, F.text)
async def lead_time(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.update_data(preferred_time=message.text.strip()[:100])
    await state.clear()
    lead = db.create_lead(
        name=data["name"],
        phone=data["phone"],
        service=data["service"],
        preferred_time=data["preferred_time"],
        source="telegram",
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
    )
    await message.answer(
        f"Готово! Заявка <b>#{lead['id']}</b> прийнята ✅\n"
        "Майстер напише вам найближчим часом, щоб підтвердити час.",
        reply_markup=main_menu(),
    )
    await notify_admin(bot, lead)


# ---------- Адмінська частина ----------

@router.callback_query(F.data.startswith("st:"))
async def change_status(call: CallbackQuery, bot: Bot) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("Недостатньо прав", show_alert=True)
        return
    _, lead_id, status = call.data.split(":")
    lead = db.set_status(int(lead_id), status)
    if lead is None:
        await call.answer("Заявку не знайдено", show_alert=True)
        return
    await call.message.edit_text(format_lead(lead), reply_markup=status_kb(lead["id"]))
    await call.answer(f"Статус: {STATUSES[status]}")
    # Повідомляємо клієнта, якщо заявка прийшла з Telegram
    if lead["tg_user_id"] and status in ("in_progress", "done"):
        text = {
            "in_progress": f"Вашу заявку #{lead['id']} взято в роботу. До зустрічі! 💈",
            "done": f"Дякуємо, що обрали {escape(BUSINESS_NAME)}! Будемо раді бачити знову ✂️",
        }[status]
        try:
            await bot.send_message(lead["tg_user_id"], text)
        except Exception:
            log.warning("Не вдалося написати клієнту %s", lead["tg_user_id"])


@router.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    leads = db.list_leads(limit=10)
    if not leads:
        await message.answer("Заявок поки немає.")
        return
    for lead in reversed(leads):
        await message.answer(format_lead(lead), reply_markup=status_kb(lead["id"]))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    s = db.stats()
    lines = [f"📊 <b>Статистика</b>", f"Сьогодні: {s['today']}", f"Усього: {s['total']}"]
    lines += [f"{label}: {s[key]}" for key, label in STATUSES.items()]
    await message.answer("\n".join(lines))


@router.message()
async def fallback(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await message.answer("Будь ласка, дайте відповідь на попереднє питання або натисніть «Скасувати».")
    else:
        await message.answer("Щоб записатися, натисніть «Записатися» 👇", reply_markup=main_menu())
