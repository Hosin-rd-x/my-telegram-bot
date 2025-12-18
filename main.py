import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات اصلی ---
TOKEN = '8513310766:AAGAGtGLTFWdv6v8zmqgJnmma2no60OOWQo'
DB_FILE = 'video_db.json'
CHANNEL_ID = -1003204294473  
INVITE_LINK = 'https://t.me/+4iAk0H9HSkk2YmZk'

# وب‌سرور برای زنده نگه داشتن در Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active!")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# مدیریت دیتابیس با قفل برای جلوگیری از تداخل
db_lock = threading.Lock()

def load_db():
    with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                try: return json.load(f)
                except: return {}
        return {}

def save_db(db):
    with db_lock:
        with open(DB_FILE, 'w') as f:
            json.dump(db, f, indent=4)

user_collections = {}
last_bot_msg = {}

# چک کردن عضویت
async def is_subscribed(context, user_id):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

def main_reply_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("📁 شروع ساخت آلبوم جدید")]], resize_keyboard=True, persistent=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        if not await is_subscribed(context, user_id):
            keyboard = [[InlineKeyboardButton("📢 عضویت در گروه", url=INVITE_LINK)]]
            await update.message.reply_text("⚠️ ابتدا عضو گروه شوید و سپس دوباره روی لینک بزنید.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        db = load_db()
        files = db.get(context.args[0])
        if files:
            sent_msgs = []
            for item in files:
                try:
                    f_id, f_type = item['id'], item['type']
                    if f_type == 'video': m = await context.bot.send_video(update.effective_chat.id, f_id)
                    elif f_type == 'photo': m = await context.bot.send_photo(update.effective_chat.id, f_id)
                    elif f_type == 'doc': m = await context.bot.send_document(update.effective_chat.id, f_id)
                    sent_msgs.append(m.message_id)
                except: continue
            
            del_msg = await update.message.reply_text("⏳ این فایل‌ها برای امنیت ۳۰ ثانیه دیگر پاک می‌شوند.")
            sent_msgs.append(del_msg.message_id)
            asyncio.create_task(delete_all_after_delay(context, update.effective_chat.id, sent_msgs, 30))
        else:
            await update.message.reply_text("❌ آلبوم یافت نشد.")
    else:
        await update.message.reply_text("خوش آمدید! برای شروع از دکمه زیر استفاده کنید:", reply_markup=main_reply_menu())

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message
    if not msg: return

    if msg.text == "📁 شروع ساخت آلبوم جدید":
        if user_id in last_bot_msg:
            try: await context.bot.delete_message(update.effective_chat.id, last_bot_msg[user_id])
            except: pass
        
        user_collections[user_id] = []
        keyboard = [[InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish_album')], [InlineKeyboardButton("❌ لغو", callback_data='cancel_album')]]
        res = await msg.reply_text("🚀 حالت ساخت آلبوم فعال شد.\nعکس، ویدیو یا فایل‌های خود را بفرستید:", reply_markup=InlineKeyboardMarkup(keyboard))
        last_bot_msg[user_id] = res.message_id

    elif user_id in user_collections:
        file_data = None
        if msg.video: file_data = {'id': msg.video.file_id, 'type': 'video'}
        elif msg.photo: file_data = {'id': msg.photo[-1].file_id, 'type': 'photo'}
        elif msg.document: file_data = {'id': msg.document.file_id, 'type': 'doc'}
        
        if file_data:
            user_collections[user_id].append(file_data)
            if user_id in last_bot_msg:
                try: await context.bot.delete_message(update.effective_chat.id, last_bot_msg[user_id])
                except: pass
            
            keyboard = [[InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish_album')], [InlineKeyboardButton("❌ لغو", callback_data='cancel_album')]]
            count = len(user_collections[user_id])
            res = await msg.reply_text(f"✅ فایل شماره {count} دریافت شد.\nمی‌توانید فایل بعدی را بفرستید یا تمام کنید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
            last_bot_msg[user_id] = res.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'finish_album':
        if not user_collections.get(user_id):
            await query.message.reply_text("⚠️ لیست خالی است!")
            return
        
        db = load_db()
        new_id = str(len(db) + 1001) # شروع از ۱۰۰۱ برای ظاهر بهتر لینک
        db[new_id] = user_collections.pop(user_id)
        save_db(db)
        
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={new_id}"
        await query.edit_message_text(f"✅ آلبوم ساخته شد!\nتعداد فایل‌ها: {len(db[new_id])}\n\n🔗 لینک شما:\n`{link}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📤 اشتراک‌گذاری", url=f"https://t.me/share/url?url={link}")]]), parse_mode='Markdown')
        last_bot_msg.pop(user_id, None)

    elif query.data == 'cancel_album':
        user_collections.pop(user_id, None)
        last_bot_msg.pop(user_id, None)
        await query.edit_message_text("❌ عملیات ساخت آلبوم لغو شد.")

async def delete_all_after_delay(context, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for m_id in message_ids:
        try: await context.bot.delete_message(chat_id, m_id)
        except: pass

if __name__ == '__main__':
    threading.Thread(target=run_health_check, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_messages))
    app.run_polling()
    
