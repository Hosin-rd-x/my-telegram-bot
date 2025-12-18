import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# توکن خودت رو اینجا بزار
TOKEN = 8513310766:AAHJgIGpmnp-JpQvFtQp8f2WeEV_LDyGRlg
DB_FILE = 'video_db.json'

# --- وب‌سرور برای زنده نگه داشتن در Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
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
            asyncio.create_task(delete_all_after_delay(context, update.effective_chat.id, sent_messages, 30))
        else:
            await update.message.reply_text("ویدیو یافت نشد.")
    else:
        await update.message.reply_text("سلام! با /new شروع کنید.")

async def new_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_collections[user_id] = []
    await update.message.reply_text("✅ حالت آلبوم فعال شد.")

async def finish_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_collections or not user_collections[user_id]:
        await update.message.reply_text("ابتدا ویدیو بفرستید.")
        return
    db = load_db()
    files = user_collections.pop(user_id)
    new_index = str(len(db) + 1)
    db[new_index] = files
    save_db(db)
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(f"✅ لینک آلبوم:\n`https://t.me/{bot_username}?start={new_index}`", parse_mode='Markdown')

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_collections:
        user_collections[user_id].append(update.message.video.file_id)
    else:
        db = load_db()
        new_index = str(len(db) + 1)
        db[new_index] = [update.message.video.file_id]
        save_db(db)
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(f"✅ لینک تکی:\n`https://t.me/{bot_username}?start={new_index}`", parse_mode='Markdown')

async def delete_all_after_delay(context, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for m_id in message_ids:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=m_id)
        except: pass

if __name__ == '__main__':
    # اجرای وب‌سرور در یک ترد جداگانه
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # اجرای ربات
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_album))
    app.add_handler(CommandHandler("finish", finish_album))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.run_polling()
  
