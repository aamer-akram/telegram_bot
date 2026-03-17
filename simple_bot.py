import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت يعمل!")

def main():
    if not TOKEN:
        print("❌ لا يوجد توكن")
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("✅ بوت الاختبار يعمل...")
    app.run_polling()

if __name__ == '__main__':
    main()