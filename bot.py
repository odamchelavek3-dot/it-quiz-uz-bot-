
import os
import json
import logging
from pathlib import Path
from datetime import datetime, time, date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    PollHandler,
)

from google import genai

# ==============================
# SOZLAMALAR
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

TZ = ZoneInfo("Asia/Tashkent")
START_DATE = date(2026, 11, 16)

DATA_FILE = Path("stats.json")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

if not TOKEN or not CHANNEL_ID or not GEMINI_API_KEY:
    raise ValueError("BOT_TOKEN, CHANNEL_ID yoki GEMINI_API_KEY topilmadi!")

client = genai.Client(api_key=GEMINI_API_KEY)


# ==============================
# STATISTIKA
# ==============================

def load_stats():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"days": {}}


def save_stats(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


stats = load_stats()


def today_key():
    return datetime.now(TZ).date().isoformat()


def save_poll_count(poll):
    key = today_key()
    stats["days"].setdefault(key, {})
    stats["days"][key][poll.id] = poll.total_voter_count
    save_stats(stats)


async def poll_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.poll:
        save_poll_count(update.poll)


# ==============================
# SAVOLLAR YARATISH
# ==============================

def get_topic():
    today = datetime.now(TZ).date()
    days = (today - START_DATE).days

    if days < 0:
        days = 0

    return "IT" if days % 2 == 0 else "HAYOTIY"


def generate_questions(topic):
    prompt = f"""
O'zbek tilida 25 ta {topic} mavzusida test yarat.

Har bir savolda:
- question: savol matni
- options: aynan 4 ta javob varianti
- answer: to'g'ri javobning 0 dan 3 gacha indeksi
- explanation: qisqa tushuntirish

Faqat quyidagi JSON formatida javob ber:
{{
  "questions": [
    {{
      "question": "Savol?",
      "options": ["A", "B", "C", "D"],
      "answer": 0,
      "explanation": "Izoh"
    }}
  ]
}}

Savollar takrorlanmasin. To'g'ri javob aniq bo'lsin.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    result = json.loads(response.text)
    questions = result["questions"]

    if len(questions) != 25:
        raise ValueError("AI 25 ta savol yaratmadi!")

    for q in questions:
        if (
            len(q["options"]) != 4
            or not isinstance(q["answer"], int)
            or q["answer"] not in range(4)
        ):
            raise ValueError("Savol formati noto'g'ri!")

    return questions


# ==============================
# KUNLIK TEST
# ==============================

async def daily_quiz(context: ContextTypes.DEFAULT_TYPE):
    topic = get_topic()

    try:
        questions = generate_questions(topic)
    except Exception:
        logger.exception("Savollarni yaratishda xatolik")
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text="⚠️ Bugungi test savollarini tayyorlashda xatolik yuz berdi."
        )
        return

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=(
            f"🎯 IT QUIZ UZ\n\n"
            f"Bugungi mavzu: {topic}\n"
            f"Jami savollar: 25\n\n"
            f"Omad!"
        ),
    )

    for number, q in enumerate(questions, start=1):
        try:
            await context.bot.send_poll(
                chat_id=CHANNEL_ID,
                question=f"{number}/25. {q['question']}",
                options=q["options"],
                type="quiz",
                correct_option_id=q["answer"],
                is_anonymous=True,
                explanation=q.get("explanation", ""),
            )
        except Exception:
            logger.exception("Test yuborilmadi: %s", number)


# ==============================
# KUNLIK STATISTIKA
# ==============================

async def daily_statistics(context: ContextTypes.DEFAULT_TYPE):
    key = today_key()
    daily = stats["days"].get(key, {})

    total_votes = sum(daily.values())
    total_questions = len(daily)

    message = (
        "📊 IT QUIZ UZ — KUNLIK STATISTIKA\n\n"
        f"📅 Sana: {key}\n"
        f"📝 Yuborilgan testlar: {total_questions}\n"
        f"👥 Jami ovozlar: {total_votes}\n\n"
        "Ishtirokingiz uchun rahmat! 🎉"
    )

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=message,
    )


# ==============================
# BOTNI ISHGA TUSHIRISH
# ==============================

async def post_init(application):
    application.job_queue.run_daily(
        daily_quiz,
        time(hour=8, minute=0, tzinfo=TZ),
        name="daily_quiz",
    )

    application.job_queue.run_daily(
        daily_statistics,
        time(hour=20, minute=0, tzinfo=TZ),
        name="daily_statistics",
    )

    logger.info("IT QUIZ UZ ishga tushdi!")


def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(PollHandler(poll_update))

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
