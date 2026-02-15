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

# Get token from Railway environment variable
TOKEN = os.getenv("BOT_TOKEN")

model = whisper.load_model("tiny")

EXCEL_FILE = "expenses.xlsx"


# =========================
# Extract Amount & Category
# =========================
def extract_details(text):
    text = text.lower()

    amount_match = re.search(r"\d+", text)
    amount = int(amount_match.group()) if amount_match else None

    categories = [
        "food", "groceries", "travel", "shopping",
        "rent", "movie", "petrol", "medicine", "fees"
    ]

    category = "other"

    for cat in categories:
        if cat in text:
            category = cat
            break

    return amount, category


# =========================
# Save Expense
# =========================
def save_expense(amount, category):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE)
    else:
        df = pd.DataFrame(columns=["Date", "Time", "Category", "Amount"])

    new_row = {
        "Date": today,
        "Time": current_time,
        "Category": category,
        "Amount": amount
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    daily_total = df[df["Date"] == today]["Amount"].sum()

    df.to_excel(EXCEL_FILE, index=False)

    return daily_total


# =========================
# Handle Voice
# =========================
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):

    voice = await update.message.voice.get_file()
    await voice.download_to_drive("voice.ogg")

    subprocess.run("ffmpeg -y -i voice.ogg voice.wav", shell=True)

    result = model.transcribe("voice.wav")
    text = result["text"]

    amount, category = extract_details(text)

    if amount is None:
        await update.message.reply_text(
            "❌ Please say clearly like: 'Spent 200 on groceries'"
        )
        return

    total_today = save_expense(amount, category)

    reply = f"""
✅ Expense Recorded!

📝 Text: {text}
📂 Category: {category}
💰 Amount: ₹{amount}

📅 Total Spent Today: ₹{total_today}
"""

    await update.message.reply_text(reply)


# =========================
# Start Command
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎤 Send voice like: 'Spent 200 on groceries'"
    )


# =========================
# Main
# =========================
def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set in environment variables!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
