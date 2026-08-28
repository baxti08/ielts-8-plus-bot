from aiogram import F, Router
from aiogram.types import Message

from bot import texts
from bot.keyboards.inline import prices_keyboard, results_keyboard
from bot.keyboards.reply import BTN_PRICES, BTN_RESULTS

router = Router(name="results_prices")


@router.message(F.text == BTN_PRICES)
async def show_prices(message: Message):
    await message.answer(texts.prices_text(), reply_markup=prices_keyboard())


@router.message(F.text == BTN_RESULTS)
async def show_results(message: Message):
    await message.answer(texts.results_text(), reply_markup=results_keyboard())
