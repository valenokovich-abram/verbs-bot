
#----------------------------------------------------------------
import asyncio
import os
import logging
import random
import sqlite3
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")
DB_NAME = "verbs_bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
router = Router()

VERBS = [
    ("be", "was/were", "been", "быть"),
    ("become", "became", "become", "становиться"),
    ("begin", "began", "begun", "начинать"),
    ("break", "broke", "broken", "ломать"),
    ("bring", "brought", "brought", "приносить"),
    ("build", "built", "built", "строить"),
    ("buy", "bought", "bought", "покупать"),
    ("catch", "caught", "caught", "ловить"),
    ("choose", "chose", "chosen", "выбирать"),
    ("come", "came", "come", "приходить"),
    ("cost", "cost", "cost", "стоить"),
    ("cut", "cut", "cut", "резать"),
    ("do", "did", "done", "делать (например, ...homework)"),
    ("draw", "drew", "drawn", "рисовать"),
    ("drink", "drank", "drunk", "пить"),
    ("drive", "drove", "driven", "водить"),
    ("eat", "ate", "eaten", "есть"),
    ("fall", "fell", "fallen", "падать"),
    ("feel", "felt", "felt", "чувствовать"),
    ("find", "found", "found", "находить"),
    ("fly", "flew", "flown", "летать"),
    ("forget", "forgot", "forgotten", "забывать"),
    ("get", "got", "got/gotten", "получать"),
    ("give", "gave", "given", "давать"),
    ("go", "went", "gone", "идти"),
    ("grow", "grew", "grown", "расти"),
    ("have", "had", "had", "иметь"),
    ("hear", "heard", "heard", "слышать"),
    ("hide", "hid", "hidden", "прятать"),
    ("hit", "hit", "hit", "ударять"),
    ("hold", "held", "held", "держать"),
    ("keep", "kept", "kept", "хранить"),
    ("know", "knew", "known", "знать"),
    ("leave", "left", "left", "уходить"),
    ("lose", "lost", "lost", "терять"),
    ("make", "made", "made", "делать (например, ...coffee)"),
    ("meet", "met", "met", "встречать"),
    ("pay", "paid", "paid", "платить"),
    ("put", "put", "put", "класть"),
    ("read", "read", "read", "читать"),
    ("ride", "rode", "ridden", "ездить"),
    ("run", "ran", "run", "бегать"),
    ("say", "said", "said", "говорить"),
    ("see", "saw", "seen", "видеть"),
    ("sell", "sold", "sold", "продавать"),
    ("send", "sent", "sent", "отправлять"),
    ("sing", "sang", "sung", "петь"),
    ("sit", "sat", "sat", "сидеть"),
    ("sleep", "slept", "slept", "спать"),
    ("speak", "spoke", "spoken", "разговаривать"),
    ("spend", "spent", "spent", "тратить"),
    ("stand", "stood", "stood", "стоять"),
    ("steal", "stole", "stolen", "красть"),
    ("swim", "swam", "swum", "плавать"),
    ("take", "took", "taken", "брать"),
    ("teach", "taught", "taught", "учить"),
    ("tell", "told", "told", "рассказывать"),
    ("think", "thought", "thought", "думать"),
    ("understand", "understood", "understood", "понимать"),
    ("wear", "wore", "worn", "носить"),
    ("win", "won", "won", "побеждать"),
    ("write", "wrote", "written", "писать"),
]


class TrainingStates(StatesGroup):
    training = State()


@dataclass
class Question:
    verb: tuple


def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            total_correct INTEGER NOT NULL DEFAULT 0,
            total_wrong INTEGER NOT NULL DEFAULT 0,
            total_skipped INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verb_stats (
            user_id INTEGER NOT NULL,
            verb TEXT NOT NULL,
            correct INTEGER NOT NULL DEFAULT 0,
            wrong INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            last_result TEXT,
            last_seen INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, verb)
        )
    """)
    connection.commit()
    connection.close()


def ensure_user(user_id: int):
    connection = db()
    connection.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,),
    )
    connection.commit()
    connection.close()


def get_user_stats(user_id: int):
    ensure_user(user_id)
    connection = db()
    row = connection.execute("""
        SELECT total_correct, total_wrong, total_skipped
        FROM users WHERE user_id = ?
    """, (user_id,)).fetchone()
    connection.close()
    return row or (0, 0, 0)


def get_verb_stats(user_id: int, verb_name: str):
    connection = db()
    row = connection.execute("""
        SELECT correct, wrong, skipped, streak, last_result
        FROM verb_stats
        WHERE user_id = ? AND verb = ?
    """, (user_id, verb_name)).fetchone()
    connection.close()
    return row or (0, 0, 0, 0, None)


def save_result(user_id: int, verb: tuple, result: str):
    ensure_user(user_id)
    verb_name = verb[0]
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO verb_stats (user_id, verb)
        VALUES (?, ?)
    """, (user_id, verb_name))

    if result == "correct":
        cursor.execute(
            "UPDATE users SET total_correct = total_correct + 1 WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute("""
            UPDATE verb_stats SET
                correct = correct + 1,
                streak = streak + 1,
                last_result = 'correct',
                last_seen = strftime('%s', 'now')
            WHERE user_id = ? AND verb = ?
        """, (user_id, verb_name))

    elif result == "wrong":
        cursor.execute(
            "UPDATE users SET total_wrong = total_wrong + 1 WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute("""
            UPDATE verb_stats SET
                wrong = wrong + 1,
                streak = 0,
                last_result = 'wrong',
                last_seen = strftime('%s', 'now')
            WHERE user_id = ? AND verb = ?
        """, (user_id, verb_name))

    elif result == "skipped":
        cursor.execute(
            "UPDATE users SET total_skipped = total_skipped + 1 WHERE user_id = ?",
            (user_id,),
        )
        cursor.execute("""
            UPDATE verb_stats SET
                skipped = skipped + 1,
                streak = 0,
                last_result = 'skipped',
                last_seen = strftime('%s', 'now')
            WHERE user_id = ? AND verb = ?
        """, (user_id, verb_name))

    connection.commit()
    connection.close()


def get_verb_weight(user_id: int, verb: tuple) -> float:
    correct, wrong, skipped, streak, last_result = get_verb_stats(
        user_id, verb[0]
    )
    weight = 10.0 + wrong * 3.0 + skipped * 2.0
    weight -= correct * 0.3
    weight -= streak * 0.8
    if last_result == "wrong":
        weight += 8.0
    if last_result == "skipped":
        weight += 5.0
    return max(weight, 0.5)


def choose_verb(
    user_id: int,
    exclude: Optional[str] = None,
    weak_only: bool = False,
):
    if weak_only:
        available = []
        for verb in VERBS:
            _, wrong, skipped, _, _ = get_verb_stats(user_id, verb[0])
            if wrong > 0 or skipped > 0:
                available.append(verb)
    else:
        available = VERBS[:]

    if exclude and len(available) > 1:
        available = [v for v in available if v[0] != exclude]

    if not available:
        available = VERBS[:]

    weights = [get_verb_weight(user_id, verb) for verb in available]
    return random.choices(available, weights=weights, k=1)[0]


def normalize_word(word: str) -> str:
    return word.strip().lower().replace(" ", "")


def split_answer(text: str):
    text = text.lower().strip()
    for separator in [",", ";", "/", "|", "-", "\n"]:
        text = text.replace(separator, " ")
    return [
        normalize_word(word)
        for word in text.split()
        if word.strip()
    ]


def form_matches(user_answer: str, correct_answer: str) -> bool:
    variants = [
        normalize_word(value)
        for value in correct_answer.split("/")
    ]
    return normalize_word(user_answer) in variants


def check_answer(text: str, verb: tuple, mode: str):
    user_forms = split_answer(text)
    correct_forms = (
        [verb[0], verb[1]]
        if mode == "first_second"
        else [verb[0], verb[1], verb[2]]
    )

    matches = [
        i < len(user_forms)
        and form_matches(user_forms[i], correct_forms[i])
        for i in range(len(correct_forms))
    ]

    return {
        "correct": len(user_forms) == len(correct_forms) and all(matches),
        "user_forms": user_forms,
        "correct_forms": correct_forms,
        "matches": matches,
    }


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_answer_feedback(result: dict) -> str:
    user_forms = result["user_forms"]
    correct_forms = result["correct_forms"]
    matches = result["matches"]

    names = (
        ["1-я форма", "2-я форма"]
        if len(correct_forms) == 2
        else ["1-я форма", "2-я форма", "3-я форма"]
    )

    lines = []
    for index, correct_form in enumerate(correct_forms):
        if index >= len(user_forms):
            lines.append(
                f"❌ <b>{names[index]}</b>: пропущено → "
                f"<b>{escape_html(correct_form)}</b>"
            )
        elif matches[index]:
            lines.append(
                f"✅ <b>{names[index]}</b>: "
                f"<b>{escape_html(user_forms[index])}</b>"
            )
        else:
            lines.append(
                f"❌ <b>{names[index]}</b>: "
                f"<s>{escape_html(user_forms[index])}</s> → "
                f"<b>{escape_html(correct_form)}</b>"
            )
    return "\n".join(lines)


def start_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚀 Старт")]],
        resize_keyboard=True,
    )


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📚 Учить глаголы"),
                KeyboardButton(text="🔥 Работа над ошибками"),
            ],
            [KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
    )


def training_modes_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1️⃣ Первая форма → вторая форма",
                    callback_data="mode_first_second",
                )
            ],
            [
                InlineKeyboardButton(
                    text="2️⃣ Все три формы",
                    callback_data="mode_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="home",
                )
            ],
        ]
    )


def weak_modes_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1️⃣ Работа над ошибками: первая форма → вторая форма",
                    callback_data="weak_first_second",
                )
            ],
            [
                InlineKeyboardButton(
                    text="2️⃣ Работа над ошибками: все три формы",
                    callback_data="weak_all",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="home",
                )
            ],
        ]
    )


def training_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="skip",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Завершить",
                    callback_data="stop",
                )
            ],
        ]
    )


def home_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="home",
                )
            ]
        ]
    )


async def ask_question(
    message: Message,
    state: FSMContext,
    user_id: int,
    exclude: Optional[str] = None,
):
    data = await state.get_data()
    mode = data.get("mode", "all")
    weak_only = data.get("weak_only", False)

    verb = choose_verb(
        user_id=user_id,
        exclude=exclude,
        weak_only=weak_only,
    )

    await state.update_data(
        question=Question(verb=verb),
        current_verb=verb[0],
    )

    if mode == "first_second":
        instruction = (
            "Напиши <b>первую и вторую формы</b> через пробел.\n\n"
            "Например:\n<code>go went</code>"
        )
    else:
        instruction = (
            "Напиши <b>все три формы</b> через пробел.\n\n"
            "Например:\n<code>go went gone</code>"
        )

    title = (
        "🔥 <b>Работа над ошибками</b>\n\n"
        if weak_only
        else "🎯 <b>Как будет по-английски?</b>\n\n"
    )

    await message.answer(
        title
        + f"🇷🇺 <b>{escape_html(verb[3])}</b>\n\n"
        + instruction
        + "\n\nЕсли не знаешь — нажми «Пропустить».",
        reply_markup=training_menu(),
    )


async def start_training(
    message: Message,
    state: FSMContext,
    mode: str,
    weak_only: bool,
):
    await state.clear()
    await state.set_state(TrainingStates.training)
    await state.update_data(
        mode=mode,
        weak_only=weak_only,
        questions=0,
        correct=0,
        wrong=0,
        skipped=0,
        question=None,
    )

    if weak_only:
        title = "🔥 <b>Работа над ошибками</b>"
    else:
        title = "📚 <b>Обучение началось!</b>"

    if mode == "first_second":
        mode_text = "Первая форма → вторая форма: <code>go went</code>"
    else:
        mode_text = "Все три формы: <code>go went gone</code>"

    await message.answer(
        f"{title}\n\n"
        f"Режим: <b>{mode_text}</b>\n\n"
        "Глаголы, в которых была допущена ошибка, будут повторяться чаще."
    )

    await ask_question(
        message,
        state,
        message.from_user.id,
    )


def has_weak_verbs(user_id: int) -> bool:
    connection = db()
    count = connection.execute("""
        SELECT COUNT(*)
        FROM verb_stats
        WHERE user_id = ?
          AND (wrong > 0 OR skipped > 0)
    """, (user_id,)).fetchone()[0]
    connection.close()
    return count > 0


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id)
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я помогу тебе выучить неправильные английские глаголы.\n\n"
        "Нажми <b>🚀 Старт</b>, чтобы открыть меню.",
        reply_markup=start_menu(),
    )


@router.message(F.text == "🚀 Старт")
async def start_button_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu(),
    )


@router.message(F.text == "📚 Учить глаголы")
async def learn_button_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📚 <b>Выбери вариант обучения:</b>\n\n"
        "1️⃣ <b>Первая форма → вторая форма</b>\n"
        "Например: <code>go went</code>\n\n"
        "2️⃣ <b>Все три формы</b>\n"
        "Например: <code>go went gone</code>",
        reply_markup=training_modes_menu(),
    )


@router.message(F.text == "🔥 Работа над ошибками")
async def weak_button_handler(message: Message, state: FSMContext):
    await state.clear()

    if not has_weak_verbs(message.from_user.id):
        await message.answer(
            "🔥 <b>Неверных глаголов пока нет.</b>\n\n"
            "Сначала пройди обычную тренировку. "
            "Ошибки и пропущенные глаголы автоматически "
            "появятся здесь.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        "🔥 <b>Работа над ошибками</b>\n\n"
        "Выбери режим:",
        reply_markup=weak_modes_menu(),
    )


@router.message(F.text == "📊 Статистика")
async def stats_button_handler(message: Message):
    await show_statistics(message, message.from_user.id)


@router.callback_query(F.data == "mode_first_second")
async def mode_first_second_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_training(callback.message, state, "first_second", False)


@router.callback_query(F.data == "mode_all")
async def mode_all_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_training(callback.message, state, "all", False)


@router.callback_query(F.data == "weak_first_second")
async def weak_first_second_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_training(callback.message, state, "first_second", True)


@router.callback_query(F.data == "weak_all")
async def weak_all_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_training(callback.message, state, "all", True)


@router.callback_query(F.data == "home")
async def home_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🏠 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.message(TrainingStates.training, F.text)
async def answer_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("question")

    if not question:
        await state.clear()
        await message.answer(
            "Произошла ошибка состояния. Начни тренировку заново.",
            reply_markup=main_menu(),
        )
        return

    mode = data.get("mode", "all")
    verb = question.verb
    user_id = message.from_user.id

    result = check_answer(message.text, verb, mode)
    questions = data.get("questions", 0) + 1
    previous_verb = verb[0]

    if result["correct"]:
        save_result(user_id, verb, "correct")
        correct_count = data.get("correct", 0) + 1
        await state.update_data(
            questions=questions,
            correct=correct_count,
        )

        if mode == "first_second":
            forms = f"{escape_html(verb[0])} — {escape_html(verb[1])}"
        else:
            forms = (
                f"{escape_html(verb[0])} — "
                f"{escape_html(verb[1])} — "
                f"{escape_html(verb[2])}"
            )

        await message.answer(
            "✅ <b>Правильно!</b>\n\n"
            f"🇷🇺 {escape_html(verb[3])}\n"
            f"🇬🇧 <b>{forms}</b>"
        )
    else:
        save_result(user_id, verb, "wrong")
        wrong_count = data.get("wrong", 0) + 1

        await state.update_data(
            questions=questions,
            wrong=wrong_count,
        )

        await message.answer(
            "❌ <b>Есть ошибка.</b>\n\n"
            f"🇷🇺 {escape_html(verb[3])}\n\n"
            f"{format_answer_feedback(result)}\n\n"
            "🔄 Этот глагол теперь будет попадаться чаще."
        )

    await ask_question(
        message,
        state,
        user_id,
        exclude=previous_verb,
    )


@router.callback_query(F.data == "skip")
async def skip_handler(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() != TrainingStates.training.state:
        await callback.answer("Тренировка не запущена.")
        return

    data = await state.get_data()
    question = data.get("question")

    if not question:
        await callback.answer("Ошибка состояния.")
        return

    verb = question.verb
    user_id = callback.from_user.id

    save_result(user_id, verb, "skipped")

    await state.update_data(
        questions=data.get("questions", 0) + 1,
        skipped=data.get("skipped", 0) + 1,
    )

    mode = data.get("mode", "all")
    if mode == "first_second":
        forms = f"{escape_html(verb[0])} — {escape_html(verb[1])}"
    else:
        forms = (
            f"{escape_html(verb[0])} — "
            f"{escape_html(verb[1])} — "
            f"{escape_html(verb[2])}"
        )

    await callback.message.answer(
        "⏭ <b>Пропускаем.</b>\n\n"
        f"🇷🇺 {escape_html(verb[3])}\n\n"
        f"Правильный ответ:\n<b>{forms}</b>\n\n"
        "🔄 Этот глагол будет попадаться чаще."
    )

    await callback.answer()

    await ask_question(
        callback.message,
        state,
        user_id,
        exclude=verb[0],
    )


@router.callback_query(F.data == "stop")
async def stop_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    await state.clear()

    await callback.message.answer(
        "🛑 <b>Тренировка завершена</b>\n\n"
        f"📚 Вопросов: <b>{data.get('questions', 0)}</b>\n"
        f"✅ Правильных: <b>{data.get('correct', 0)}</b>\n"
        f"❌ Ошибок: <b>{data.get('wrong', 0)}</b>\n"
        f"⏭ Пропущено: <b>{data.get('skipped', 0)}</b>",
        reply_markup=main_menu(),
    )
    await callback.answer()


def get_weak_verbs(user_id: int, limit: int = 7):
    connection = db()
    result = connection.execute("""
        SELECT verb, correct, wrong, skipped, streak
        FROM verb_stats
        WHERE user_id = ?
          AND (wrong > 0 OR skipped > 0)
        ORDER BY wrong DESC, skipped DESC, streak ASC
        LIMIT ?
    """, (user_id, limit)).fetchall()
    connection.close()
    return result


async def show_statistics(message: Message, user_id: int):
    correct, wrong, skipped = get_user_stats(user_id)
    total = correct + wrong
    accuracy = round(correct / total * 100, 1) if total else 0

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"✅ Правильных: <b>{correct}</b>\n"
        f"❌ Ошибок: <b>{wrong}</b>\n"
        f"⏭ Пропущено: <b>{skipped}</b>\n\n"
        f"🎯 Проверено: <b>{total}</b>\n"
        f"📈 Точность: <b>{accuracy}%</b>"
    )

    weak = get_weak_verbs(user_id)
    if weak:
        text += "\n\n🔥 <b>Нужно повторить:</b>\n"
        for verb, correct_count, wrong_count, skipped_count, streak in weak:
            text += (
                f"\n• <b>{escape_html(verb)}</b>"
                f" — ❌ {wrong_count}"
                f" / ⏭ {skipped_count}"
                f" / 🔥 {streak}"
            )

    await message.answer(text, reply_markup=home_menu())


@router.message(Command("stats"))
async def stats_command_handler(message: Message):
    await show_statistics(message, message.from_user.id)


@router.callback_query(F.data == "stats")
async def statistics_callback_handler(callback: CallbackQuery):
    await callback.answer()
    await show_statistics(callback.message, callback.from_user.id)


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "ℹ️ <b>Помощь</b>\n\n"
        "🚀 Старт — главное меню.\n"
        "📚 Учить глаголы — обычная тренировка.\n"
        "🔥 Работа над ошибками — повторение ошибок и пропусков.\n"
        "📊 Статистика — результаты.\n\n"
        "В обоих режимах слабых глаголов доступны:\n"
        "1️⃣ первая форма → вторая форма;\n"
        "2️⃣ все три формы."
    )


@router.message(F.text)
async def unknown_text_handler(message: Message):
    await message.answer(
        "🤔 Я не совсем понял команду.\n\n"
        "Нажми <b>🚀 Старт</b>, чтобы открыть меню.",
        reply_markup=start_menu(),
    )


@router.errors()
async def error_handler(event):
    logger.exception("Unhandled error: %s", event.exception)


async def main():
    logger.info("Starting bot...")

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError(
            "Замени YOUR_BOT_TOKEN на настоящий токен бота."
        )

    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    try:
        me = await bot.get_me()
        logger.info("Connected to Telegram: @%s", me.username)

        dp = Dispatcher()
        dp.include_router(router)

        logger.info("Bot is ready. Starting polling...")
        await dp.start_polling(bot)

    except TelegramAPIError as error:
        logger.exception("Telegram API error: %s", error)

    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")

# ============================================================ # RUN # ============================================================
if __name__ == "__main__":
    try:         asyncio.run(main())
    except KeyboardInterrupt:         logger.info("Bot stopped manually.")
#-------------------------------------------------------------------------------------------------------------

