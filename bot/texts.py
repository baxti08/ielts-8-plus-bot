"""All Uzbek user-facing text templates in one place, exactly as specified."""
from common.config import get_settings

settings = get_settings()


def gate_message(missing_only: bool = False, channels=None) -> str:
    if not missing_only:
        return (
            "❗️ Botdan foydalanish uchun avval kanallarimizga a'zo bo'ling:\n\n"
            "A'zo bo'lgach, «✅ A'zo bo'ldim» tugmasini bosing."
        )
    return (
        "❗️ Siz hali quyidagi kanal(lar)ga a'zo bo'lmagansiz:\n\n"
        "A'zo bo'lgach, «✅ A'zo bo'ldim» tugmasini qayta bosing."
    )


def left_channel_notice() -> str:
    return (
        "⚠️ Siz majburiy kanallardan biridan chiqib ketdingiz.\n\n"
        "Botdan foydalanishni davom ettirish uchun qaytadan a'zo bo'ling va "
        "«✅ A'zo bo'ldim» tugmasini bosing."
    )


def main_menu(profile_name: str) -> str:
    return (
        f"👋 Assalomu alaykum, <b>{profile_name}</b>!\n\n"
        "🎁 <b>Ustozlar</b> kursidagi barcha VIDEO DARSLAR endi shu botda!\n\n"
        "📚 Reading, Listening, Speaking va Writing bo'yicha sifatli yozilgan darslar "
        "hamda maxsus materiallar.\n\n"
        "Videolarni olish uchun pastdagi tugmani bosing 👇"
    )


def locked_section_header(section: "Section") -> str:
    from common.db.models import DAYS_PER_SECTION  # local import to avoid a circular import at module load time

    name = section.display_name
    if section in DAYS_PER_SECTION and not name.endswith("darslari"):
        name = f"{name} darslari"
    return f"<b>🔒 {name}</b> hali siz uchun yopiq.\n\nOchish uchun 3 ta do'stingizni taklif qiling."


def referral_pitch_block(current: int, target: int, squares: str) -> str:
    return (
        "🎁 Biz <b>2,000,000 so'm</b> qiymatidagi video darsliklarni sizga <b>BEPULGA</b> beryapmiz!\n\n"
        "🙏 Bu bilimlar ko'pchilikka yetib borishida sizning yordamingiz kerak bo'ladi!\n\n"
        f"👥 Ingliz tili o'rganayotgan <b>{target} tadan do'stingizni</b> taklif qiling va bu botdagi "
        "<b>barcha video-dars va materiallar</b> siz uchun <b>BEPUL</b> ochiladi!\n\n"
        f"📊 Sizning natijangiz: <b>{current}/{target}</b>\n"
        f"{squares}\n\n"
        "✅ Do'stingiz havola orqali botga kirib, <b>kanalga a'zo bo'lsa</b> — sizga <b>1 ball</b> qo'shiladi.\n\n"
        "❗️ Kanalimizga allaqachon a'zo bo'lganlar uchun ball berilmaydi — shuning uchun havolani "
        "<b>hali obuna bo'lmagan</b> do'stlaringizga yuboring!\n\n"
        "⚠️ Do'stingiz kanaldan chiqib ketsa — bali bekor bo'ladi. Shuning uchun ingliz tilini "
        "<b>chindan o'rganadigan</b> do'stlarni taklif qiling!\n\n"
        "<b>👇 Do'stlarga yuboriladigan tayyor postni olish uchun tugmani bosing</b>"
    )


def referral_post_message(user_id: int) -> str:
    link = f"https://t.me/{settings.bot_username}?start=ref_{user_id}"
    return (
        "🎁 <b>ENG KATTA IELTS & CEFR ustozlar 2,000,000 so'mlik kurslarini BEPULGA sovg'a qilyaptilar!</b>\n\n"
        "🎬 <b>Sifatli video darslar:</b> Reading • Listening • Speaking • Writing\n\n"
        "<b>⚡️ Imkoniyatdan foydalaning — darslarni shu bot orqali bepul olishingiz mumkin 👇</b>\n\n"
        f"{link}"
    )


def referral_forward_hint() -> str:
    return (
        "👆 <b>Yuqoridagi postni do'stlaringizga yuboring!</b>\n\n"
        "Post ustiga bosib «Forward» tugmasi orqali do'stlaringiz va guruhlarga yuborishingiz mumkin.\n\n"
        "📤 Yoki pastdagi tugma orqali darhol yuboring:"
    )


def friend_joined_notice(referred_name: str, current: int, target: int, squares_str: str) -> str:
    import html

    safe_name = html.escape(referred_name) if referred_name else ""
    who = f" <b>{safe_name}</b>" if safe_name else ""
    return (
        f"👥 Do'stingiz{who} siz orqali qo'shildi!\n\n"
        f"📊 Natija: <b>{current}/{target}</b>\n"
        f"{squares_str}"
    )


def my_result_in_progress(n: int, target: int, squares: str) -> str:
    return (
        "📊 <b>Mening natijam</b>\n\n"
        f"👥 Taklif qilingan do'stlar: <b>{n}/{target}</b>\n"
        f"{squares}\n\n"
        "🔒 Dars va materiallar hali yopiq. Do'stlaringizni taklif qilishda davom eting!"
    )


def my_result_unlocked(n: int, target: int, squares: str, section_name: str) -> str:
    return (
        "📊 <b>Mening natijam</b>\n\n"
        f"👥 Taklif qilingan do'stlar: <b>{n}/{target}</b>\n"
        f"{squares}\n\n"
        f"✅ {section_name} ochilgan! «{section_name}»ni tanlang."
    )


def choose_section_prompt() -> str:
    return "🎉 Tabriklaymiz! Siz yana 1 ta bo'limni ochishga haqlisiz.\n\nQaysi bo'limni ochmoqchisiz?"


def section_unlocked_notice(section_name: str) -> str:
    return f"✅ <b>{section_name}</b> muvaffaqiyatli ochildi! Endi darslarni ko'rishingiz mumkin."


def section_relocked_notice(section_name: str) -> str:
    return (
        f"⚠️ Do'stingiz majburiy kanaldan chiqib ketgani sabab <b>{section_name}</b> "
        "bo'limi qayta yopildi.\n\nUni qayta ochish uchun yana 3 ta yangi do'stingizni taklif qiling."
    )


def prices_text() -> str:
    return (
        "💰 <b>Oldin bu kurslar va materiallar umumiy 2,000,000 UZS ga sotilgan.</b>\n\n"
        "🎁 Bularni siz <b>BEPULGA</b> olishiz mumkin!"
    )


def results_text() -> str:
    return "🏆 Bu kursda o'qigan o'quvchilarimizning natijalari 👇"


def squares(current: int, target: int) -> str:
    filled = "🟩" * min(current, target)
    empty = "⬜️" * max(target - current, 0)
    return filled + empty
