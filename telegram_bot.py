import os
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🛑 Stop and Sell All", callback_data="stop_sell")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🚀 Trading started! Control bot with button below.', reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "stop_sell":
        await context.bot_data['trader_bot'].force_sell_all()
        await query.edit_message_text(text="✅ All coins sold and bot stopped!")

async def run_telegram_bot(trader_bot_instance):
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.bot_data['trader_bot'] = trader_bot_instance
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    await application.run_polling()
