import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تنظیمات اصلی
TOKEN = '8513310766:AAHJgIGpmnp-JpQvFtQp8f2WeEV_LDyGRlg'
DB_FILE = 'video_db.json'

# --- وب‌سرور برای زنده نگه داشتن ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# --- توابع دیتابیس ---
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f)

user_collections = {}

# --- منوی اصلی ---
def main_menu():
    keyboard = [[InlineKeyboardButton("📁 شروع ساخت آلبوم جدید", callback_data='new_album')]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    # اگر کاربر با لینک استارت زده باشد
    if context.args:
        group_id = context.args[0]
        files = db.get(group_id)
        if files:
            file_list = files if isinstance(files, list) else [files]
            sent_messages = []
            for file_id in file_list:
                try:
                    msg = await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id)
                    sent_messages.append(msg.message_id)
                except: continue
            await update.message.reply_text("⏳ ویدیوها ارسال شد. ۳۰ ثانیه دیگر پاک می‌شوند.")
            asyncio.create_task(delete_all_after_delay(context, update.effective_chat.id, sent_messages, 30))
        else:
            await update.message.reply_text("❌ یافت نشد.")
    else:
        await update.message.reply_text("به ربات مدیریت ویدیو خوش آمدید! یکی از گزینه‌ها را انتخاب کنید:", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'new_album':
        user_collections[user_id] = []
        keyboard = [[InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish_album')]]
        await query.edit_message_text("📥 حالا ویدیوهای خود را بفرستید. پس از اتمام، دکمه زیر را بزنید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'finish_album':
        if user_id not in user_collections or not user_collections[user_id]:
            await query.message.reply_text("⚠️ اول چند ویدیو بفرستید!")
            return
        
        db = load_db()
        files = user_collections.pop(user_id)
        new_index = str(len(db) + 1)
        db[new_index] = files
        save_db(db)
        
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={new_index}"
        await query.edit_message_text(f"✅ آلبوم ساخته شد!\n\nلینک اشتراک‌گذاری:\n`{link}`", parse_mode='Markdown', reply_markup=main_menu())

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_collections:
        user_collections[user_id].append(update.message.video.file_id)
        count = len(user_collections[user_id])
        keyboard = [[InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish_album')]]
        await update.message.reply_text(f"✅ ویدیو شماره {count} ذخیره شد.", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # آپلود تکی بدون دکمه (خودکار لینک می‌دهد)
        db = load_db()
        new_index = str(len(db) + 1)
        db[new_index] = [update.message.video.file_id]
        save_db(db)
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={new_index}"
        await update.message.reply_text(f"✅ لینک ویدیو تکی:\n`{link}`", parse_mode='Markdown', reply_markup=main_menu())

async def delete_all_after_delay(context, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for m_id in message_ids:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=m_id)
        except: pass

if __name__ == '__main__':
    threading.Thread(target=run_health_check, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.run_polling()
    
