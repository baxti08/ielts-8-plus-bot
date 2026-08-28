from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.config import get_settings
from common.db.models import DAYS_PER_SECTION, Section

settings = get_settings()

DAYS_PER_PAGE = 10


def gate_check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ A'zo bo'ldim", callback_data="gate_check")]]
    )


def gate_channels_keyboard(missing_only: bool = False, channels=None) -> InlineKeyboardMarkup:
    """One full-width button per required channel, then the verify button below."""
    channels = channels if channels is not None else settings.required_channels
    rows = [
        [InlineKeyboardButton(text=c["name"], url=f"https://t.me/{c['username']}")] for c in channels
    ]
    rows.append([InlineKeyboardButton(text="✅ A'zo bo'ldim", callback_data="gate_check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def locked_section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Do'stlar uchun havola", callback_data="ref_link")],
            [InlineKeyboardButton(text="🔄 Natijani ko'rsatish", callback_data="ref_progress")],
            [InlineKeyboardButton(text="◀️ Menyu", callback_data="menu")],
        ]
    )


def referral_link_share_keyboard(user_id: int) -> InlineKeyboardMarkup:
    link = f"https://t.me/{settings.bot_username}?start=ref_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Bepul darslarni olish", url=link)]])


def referral_share_button_keyboard(user_id: int) -> InlineKeyboardMarkup:
    link = f"https://t.me/{settings.bot_username}?start=ref_{user_id}"
    promo = (
        "🎁 ENG KATTA IELTS & CEFR ustozlar 2,000,000 so'mlik kurslarini BEPULGA sovg'a qilyaptilar!\n\n"
        "🎬 Sifatli video darslar: Reading • Listening • Speaking • Writing\n\n"
        "⚡️ Imkoniyatdan foydalaning — darslarni shu bot orqali bepul olishingiz mumkin 👇\n\n"
        f"{link}"
    )
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(promo)}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Do'stlarga yuborish", url=share_url)],
            [InlineKeyboardButton(text="◀️ Menyu", callback_data="menu")],
        ]
    )


def section_choice_keyboard(available_sections: list[Section]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🔓 {s.display_name}", callback_data=f"choose_section:{s.value}")]
        for s in available_sections
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def content_day_grid(section: Section, page: int) -> InlineKeyboardMarkup:
    """
    page is 0-indexed. Each page shows up to DAYS_PER_PAGE day buttons (5 per row),
    then Oldingi/Keyingi nav where applicable, then bundle + menu buttons.
    """
    total_days = DAYS_PER_SECTION[section]
    start = page * DAYS_PER_PAGE + 1
    end = min(start + DAYS_PER_PAGE - 1, total_days)

    rows = []
    day_buttons = [
        InlineKeyboardButton(text=str(d), callback_data=f"day:{section.value}:{d}")
        for d in range(start, end + 1)
    ]
    for i in range(0, len(day_buttons), 5):
        rows.append(day_buttons[i : i + 5])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page:{section.value}:{page - 1}"))
    if end < total_days:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page:{section.value}:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="📥 Shu sahifani olish", callback_data=f"bundle:{section.value}:{page}")])
    rows.append([InlineKeyboardButton(text="◀️ Menyu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prices_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Dars va materiallarni ochish", callback_data="open_lessons")],
            [InlineKeyboardButton(text="🏆 Bu kurslarda o'qiganlar natijasi", url=settings.results_link)],
            [InlineKeyboardButton(text="◀️ Menyu", callback_data="menu")],
        ]
    )


def results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏆 Natijalarni ko'rish", url=settings.results_link)]]
    )
