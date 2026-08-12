import os
import json
from datetime import date

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI


# =========================
# SETTINGS
# =========================

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

DATA_FILE = "users.json"


# =========================
# DATABASE
# =========================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


users = load_data()


def get_user(user_id):
    user_id = str(user_id)

    if user_id not in users:
        users[user_id] = {
            "profile": {},
            "today": {
                "date": str(date.today()),
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
                "meals": []
            }
        }
        save_data(users)

    user = users[user_id]

    # New day
    if user["today"]["date"] != str(date.today()):
        user["today"] = {
            "date": str(date.today()),
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "meals": []
        }
        save_data(users)

    return user


# =========================
# CALORIE GOAL
# =========================

def calculate_goal(profile):

    age = profile["age"]
    height = profile["height"]
    weight = profile["weight"]
    gender = profile["gender"]
    activity = profile["activity"]
    goal = profile["goal"]

    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    activity_factors = {
        "low": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "high": 1.725,
        "very_high": 1.9
    }

    tdee = bmr * activity_factors.get(activity, 1.55)

    if goal == "lose":
        calories = tdee - 400
    elif goal == "gain":
        calories = tdee + 300
    else:
        calories = tdee

    calories = max(1200, round(calories))

    protein = round(weight * 2)
    fat = round(weight * 0.8)

    carbs = round(
        (calories - protein * 4 - fat * 9) / 4
    )

    return {
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat
    }


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    if user["profile"]:
        await update.message.reply_text(
            "سلام 👋\n\n"
            "پروفایل تغذیه‌ای شما قبلاً ثبت شده.\n\n"
            "غذایی که خوردی رو همینجا بنویس.\n\n"
            "مثلاً:\n"
            "۳۰۰ گرم برنج + ۲۰۰ گرم مرغ + یک لیوان دوغ\n\n"
            "دستورات:\n"
            "/today گزارش امروز\n"
            "/goal هدف روزانه\n"
            "/reset صفر کردن امروز"
        )
        return

    await update.message.reply_text(
        "سلام 👋\n"
        "من ربات کالری‌شمار و تغذیه شما هستم.\n\n"
        "برای شروع چند اطلاعات لازم دارم.\n\n"
        "سن، قد، وزن، جنسیت، میزان فعالیت و هدفت رو بگو.\n\n"
        "مثال:\n"
        "25 سال، 190 سانتی‌متر، 90 کیلو، مرد، "
        "فعالیت زیاد، هدف کاهش چربی و عضله‌سازی"
    )


# =========================
# AI FOOD ANALYSIS
# =========================

async def analyze_food(text):

    prompt = f"""
تو یک دستیار حرفه‌ای محاسبه تغذیه هستی.

متن کاربر را بررسی کن و غذاهای مصرف‌شده را شناسایی کن.

برای هر غذا مقدار کالری، پروتئین، کربوهیدرات و چربی را تخمین بزن.

اگر مقدار غذا مشخص نیست، یک مقدار معمول و منطقی در نظر بگیر.

پاسخ فقط JSON معتبر باشد.

ساختار:

{{
  "foods": [
    {{
      "name": "نام غذا",
      "amount": "مقدار",
      "calories": 0,
      "protein": 0,
      "carbs": 0,
      "fat": 0
    }}
  ],
  "total": {{
    "calories": 0,
    "protein": 0,
    "carbs": 0,
    "fat": 0
  }}
}}

متن کاربر:
{text}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    result = response.output_text

    return json.loads(result)


# =========================
# MESSAGE HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()
    user_id = update.effective_user.id

    user = get_user(user_id)

    # If profile doesn't exist
    if not user["profile"]:

        prompt = f"""
اطلاعات بدنی کاربر را از متن زیر استخراج کن.

فقط JSON معتبر بده.

ساختار:

{{
"age": عدد,
"height": عدد,
"weight": عدد,
"gender": "male" یا "female",
"activity": "low" یا "light" یا "moderate" یا "high" یا "very_high",
"goal": "lose" یا "maintain" یا "gain"
}}

تفسیر فعالیت:
کم = low
سبک = light
متوسط = moderate
زیاد = high
خیلی زیاد = very_high

تفسیر هدف:
کاهش وزن/چربی = lose
حفظ وزن = maintain
افزایش وزن/عضله = gain

متن:
{text}
"""

        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        try:
            profile = json.loads(response.output_text)

            user["profile"] = profile
            user["goal"] = calculate_goal(profile)

            save_data(users)

            goal = user["goal"]

            await update.message.reply_text(
                "✅ پروفایل شما ثبت شد.\n\n"
                f"🔥 کالری روزانه: {goal['calories']} kcal\n"
                f"🥩 پروتئین: {goal['protein']} g\n"
                f"🍚 کربوهیدرات: {goal['carbs']} g\n"
                f"🥑 چربی: {goal['fat']} g\n\n"
                "حالا غذایی که خوردی رو بنویس.\n"
                "مثلاً: 300 گرم برنج و 200 گرم مرغ"
            )

        except Exception:
            await update.message.reply_text(
                "اطلاعات رو کامل متوجه نشدم 😅\n\n"
                "مثلاً بنویس:\n"
                "25 سال، 190 سانتی‌متر، 90 کیلو، مرد، "
                "فعالیت زیاد، هدف کاهش چربی"
            )

        return

    # Food analysis
    try:

        result = await analyze_food(text)

        total = result["total"]

        calories = round(total["calories"])
        protein = round(total["protein"])
        carbs = round(total["carbs"])
        fat = round(total["fat"])

        user["today"]["calories"] += calories
        user["today"]["protein"] += protein
        user["today"]["carbs"] += carbs
        user["today"]["fat"] += fat

        user["today"]["meals"].append({
            "text": text,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat
        })

        save_data(users)

        goal = user["goal"]

        remaining_calories = max(
            0,
            goal["calories"] - user["today"]["calories"]
        )

        remaining_protein = max(
            0,
            goal["protein"] - user["today"]["protein"]
        )

        remaining_carbs = max(
            0,
            goal["carbs"] - user["today"]["carbs"]
        )

        remaining_fat = max(
            0,
            goal["fat"] - user["today"]["fat"]
        )

        food_text = ""

        for food in result["foods"]:
            food_text += (
                f"• {food['name']} ({food['amount']}) — "
                f"{food['calories']} kcal\n"
            )

        message = (
            "🍽 وعده ثبت شد\n\n"
            f"{food_text}\n"
            "🔥 این وعده:\n"
            f"کالری: {calories} kcal\n"
            f"پروتئین: {protein} g\n"
            f"کربوهیدرات: {carbs} g\n"
            f"چربی: {fat} g\n\n"
            "━━━━━━━━━━━━\n"
            "📊 مجموع امروز:\n"
            f"🔥 {user['today']['calories']} / {goal['calories']} kcal\n"
            f"🥩 {user['today']['protein']} / {goal['protein']} g پروتئین\n"
            f"🍚 {user['today']['carbs']} / {goal['carbs']} g کربوهیدرات\n"
            f"🥑 {user['today']['fat']} / {goal['fat']} g چربی\n\n"
            "⏳ باقی‌مانده امروز:\n"
            f"🔥 {remaining_calories} kcal\n"
            f"🥩 {remaining_protein} g پروتئین\n"
            f"🍚 {remaining_carbs} g کربوهیدرات\n"
            f"🥑 {remaining_fat} g چربی"
        )

        await update.message.reply_text(message)

    except Exception as e:

        print("ERROR:", e)

        await update.message.reply_text(
            "متأسفانه نتونستم غذا رو تحلیل کنم 😕\n"
            "لطفاً مقدار غذا رو واضح‌تر بنویس.\n\n"
            "مثال:\n"
            "250 گرم برنج پخته + 150 گرم سینه مرغ"
        )


# =========================
# TODAY
# =========================

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    if not user["profile"]:
        await update.message.reply_text(
            "اول باید پروفایلت رو ثبت کنی. /start"
        )
        return

    goal = user["goal"]
    t = user["today"]

    await update.message.reply_text(
        "📊 گزارش امروز\n\n"
        f"🔥 کالری: {t['calories']} / {goal['calories']} kcal\n"
        f"🥩 پروتئین: {t['protein']} / {goal['protein']} g\n"
        f"🍚 کربوهیدرات: {t['carbs']} / {goal['carbs']} g\n"
        f"🥑 چربی: {t['fat']} / {goal['fat']} g\n\n"
        f"⏳ کالری باقی‌مانده: "
        f"{max(0, goal['calories'] - t['calories'])} kcal"
    )


# =========================
# GOAL
# =========================

async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    if not user["profile"]:
        await update.message.reply_text(
            "اول پروفایلت رو ثبت کن. /start"
        )
        return

    g = user["goal"]

    await update.message.reply_text(
        "🎯 هدف روزانه شما:\n\n"
        f"🔥 کالری: {g['calories']} kcal\n"
        f"🥩 پروتئین: {g['protein']} g\n"
        f"🍚 کربوهیدرات: {g['carbs']} g\n"
        f"🥑 چربی: {g['fat']} g"
    )


# =========================
# RESET
# =========================

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    user["today"] = {
        "date": str(date.today()),
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fat": 0,
        "meals": []
    }

    save_data(users)

    await update.message.reply_text(
        "♻️ گزارش امروز پاک شد.\n"
        "از الان شمارش کالری از صفر شروع می‌شود."
    )


# =========================
# RUN BOT
# =========================

def main():

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("goal", goal))
    app.add_handler(CommandHandler("reset", reset))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
