import os
import re
import whisper
import pandas as pd
import subprocess
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")

model = whisper.load_model("base")


# =========================
# CATEGORY DETECTION
# =========================
def detect_category(text):
    text = text.lower()

    category_map = {
        "food": ["food", "eat", "cake", "biryani", "snacks", "restaurant", "chocolates","staters"],
        
        "fashion": ["dress", "clothes", "shirt", "jeans", "shoes", "fashion"],
        
        "electronics": ["laptop", "mobile", "phone", "charger", "headphones", "printer"],
        
        "books": ["book", "books", "notebook", "study material"],
        
        "fees": ["fees", "college fees", "tution"],
        
        "travel": ["bus", "train", "uber", "auto", "taxi"],
        
        "petrol": ["petrol", "fuel", "diesel"],
        
        "movie": ["movie", "cinema"],
        
        "medicine": ["doctor", "hospital", "medicine"]
    }

    for category, keywords in category_map.items():
        if any(word in text for word in keywords):
            return category

    return "other"

# =========================
# MULTI EXPENSE EXTRACTION
# =========================
def extract_multiple_expenses(text):
    text = text.lower()
    parts = re.split(r'\band\b|,', text)

    expenses = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        amount_match = re.search(r"\d+(?:\.\d+)?", part)
        if not amount_match:
            continue

        amount = float(amount_match.group())

        # Clean item
        item = re.sub(r"(₹|rs\.?|inr)?\s*\d+(?:\.\d+)?", "", part)
        item = re.sub(r"\b(i|spent|paid|for|on|rupees)\b", "", item)
        item = item.strip()

        if not item:
            item = "unknown"

        category = detect_category(part)

        expenses.append((amount, category, item))

    return expenses


# =========================
# FILE PER USER
# =========================
def get_file(user_id):
    return f"expenses_{user_id}.xlsx"


# =========================
# SAVE EXPENSE + TOTAL ROW
# =========================
def save_expense(user_id, amount, category, item):
    file = get_file(user_id)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    if os.path.exists(file):
        df = pd.read_excel(file)

        for col in ["Date", "Time", "Item", "Category", "Amount"]:
            if col not in df.columns:
                df[col] = ""

        df = df[["Date", "Time", "Item", "Category", "Amount"]]
    else:
        df = pd.DataFrame(columns=["Date", "Time", "Item", "Category", "Amount"])

    # ❌ Remove ALL TOTAL rows
    df = df[df["Item"] != "TOTAL"]

    # ➕ Add new entry
    new_row = {
        "Date": today,
        "Time": current_time,
        "Item": item,
        "Category": category,
        "Amount": amount
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # ✅ Calculate ONLY today's total (excluding TOTAL rows)
    today_total = df[
        (df["Date"] == today) & (df["Item"] != "TOTAL")
    ]["Amount"].sum()

    # ➕ Add correct TOTAL row
    total_row = {
        "Date": today,
        "Time": "",
        "Item": "TOTAL",
        "Category": "",
        "Amount": today_total
    }

    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    df.to_excel(file, index=False)

    return today_total

# =========================
# HANDLE VOICE
# =========================
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # ⏳ Send early response
        await update.message.reply_text("⏳ Processing your voice...")

        user_id = update.message.from_user.id

        voice = await update.message.voice.get_file()

        file_path = f"{user_id}_voice.ogg"
        wav_path = f"{user_id}_voice.wav"

        await voice.download_to_drive(file_path)

        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        result = model.transcribe(wav_path)
        text = result["text"]

        print("📝 Transcribed:", text)

        expenses = extract_multiple_expenses(text)

        if not expenses:
            await update.message.reply_text("❌ Couldn't detect expenses.")
            return

        reply = "✅ Expenses Recorded!\n\n"

        for amount, category, item in expenses:
            save_expense(user_id, amount, category, item)
            reply += f"🧾 {item} - ₹{amount} ({category})\n"

        file = get_file(user_id)
        df = pd.read_excel(file)

        today = datetime.now().strftime("%Y-%m-%d")

        total_today = df[
            (df["Date"] == today) &
            (df["Item"] != "TOTAL")
        ]["Amount"].sum()

        reply += f"\n📅 Total Today: ₹{total_today}"

        await update.message.reply_text(reply)

    except Exception as e:
        print("❌ Error:", e)
        await update.message.reply_text(f"⚠️ Error: {str(e)}")
# =========================
# REPORT COMMAND
# =========================
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    file = get_file(user_id)

    if not os.path.exists(file):
        await update.message.reply_text("No expenses found.")
        return

    df = pd.read_excel(file)

    today = datetime.now().strftime("%Y-%m-%d")
    df_today = df[df["Date"] == today]

    if df_today.empty:
        await update.message.reply_text("No expenses for today.")
        return

    total = df_today["Amount"].sum()

    reply = f"📅 Report for {today}\n\n🧾 Expenses:\n"

    for _, row in df_today.iterrows():
        if row["Item"] != "TOTAL":
            reply += f"{row['Item']} - ₹{row['Amount']} ({row['Category']})\n"

    reply += f"\n💰 Total: ₹{total}"

    await update.message.reply_text(reply)


# =========================
# START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎤 Send voice like:\n"
        "'Spent 200 on cake and 300 on shoes'\n\n"
        "Commands:\n"
        "/report - Detailed daily report"
    )


# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot Running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()