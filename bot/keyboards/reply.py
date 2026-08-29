from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_READING = "🗂️ IELTS Reading"
BTN_LISTENING = "🎧 IELTS Listening"
BTN_SPEAKING = "🗣️ IELTS Speaking"
BTN_WRITING = "✍️ IELTS Writing"
BTN_MULTILEVEL = "🔝 Multi-Level darslari"
BTN_MORE_FEATURES = "⚡️ Ko'proq funksiyalar"
BTN_REFERRAL_LINK = "🔗 Do'stlar uchun havola"
BTN_MY_RESULT = "📊 Mening natijam"
BTN_PRICES = "💰 Narxlar"
BTN_RESULTS = "🏆 Natijalar"
BTN_MENU = "◀️ Menyu"

# Locked-state variants (🔒 prefix) shown once a gated section isn't unlocked yet.
LOCKED_LABELS = {
    "listening": "🔒 " + BTN_LISTENING,
    "speaking": "🔒 " + BTN_SPEAKING,
    "writing": "🔒 " + BTN_WRITING,
    "multilevel": "🔒 " + BTN_MULTILEVEL,
}

# Every label (locked or not) that should be treated as "open section X" when pressed.
SECTION_BUTTON_MAP = {
    BTN_READING: "reading",
    BTN_LISTENING: "listening",
    LOCKED_LABELS["listening"]: "listening",
    BTN_SPEAKING: "speaking",
    LOCKED_LABELS["speaking"]: "speaking",
    BTN_WRITING: "writing",
    LOCKED_LABELS["writing"]: "writing",
    BTN_MULTILEVEL: "multilevel",
    LOCKED_LABELS["multilevel"]: "multilevel",
}


def main_menu_keyboard(unlocked_sections: set) -> ReplyKeyboardMarkup:
    def label(base: str, section_key: str) -> str:
        if section_key in unlocked_sections:
            return base
        return LOCKED_LABELS[section_key]

    rows = [
        [KeyboardButton(text=BTN_READING)],
        [
            KeyboardButton(text=label(BTN_LISTENING, "listening")),
            KeyboardButton(text=label(BTN_SPEAKING, "speaking")),
        ],
        [
            KeyboardButton(text=label(BTN_WRITING, "writing")),
            KeyboardButton(text=label(BTN_MULTILEVEL, "multilevel")),
        ],
        [KeyboardButton(text=BTN_MORE_FEATURES)],
        [KeyboardButton(text=BTN_REFERRAL_LINK)],
        [KeyboardButton(text=BTN_MY_RESULT), KeyboardButton(text=BTN_PRICES)],
        [KeyboardButton(text=BTN_RESULTS)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Tugmani tanlang 👇")
