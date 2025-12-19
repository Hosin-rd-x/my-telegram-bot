import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات نهایی با آخرین توکن شما ---
TOKEN = '8513310766:AAH6ft6CNlR9E9a2Mx40zbXn4Ve9gMMFbNU'
# استفاده از پوشه موقت برای رفع محدودیت‌های فایل در Render
DB_FILE = '/tmp/video_db.json'
CHANNEL_ID = -1003204294473  
INVITE_LINK = 'https://t.me/+4iAk0H9HSkk2YmZk'

# وب‌سرور برای جلوگیری از غیرفعال شدن ربات در سرویس‌های ابری
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running and Active")

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# مدیریت دیتابیس
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

# حافظه موقت برای مدیریت پیام‌ها
user_collections = {}
last_bot_msg = {}

# بررسی عضویت در کانال/گروه
async def is_subscribed(context, user_id):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

def main_reply_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("📁 شروع ساخت آلبوم جدید")]], resize_keyboard=True)

# دستور شروع و نمایش آلبوم‌ها
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        if not await is_subscribed(context, user_id):
            keyboard = [[InlineKeyboardButton("📢 عضویت در کانال", url=INVITE_LINK)]]
            await update.message.reply_text("⚠️ لطفاً ابتدا عضو شوید و سپس مجدداً روی لینک کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
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
            
            del_notif = await update.message.reply_text("⏳ فایل‌ها جهت امنیت شما ۳۰ ثانیه دیگر پاک می‌شوند.")
            sent_msgs.append(del_notif.message_id)
            asyncio.create_task(delete_after_delay(context, update.effective_chat.id, sent_msgs, 30))
        else:
            await update.message.reply_text("❌ متأسفانه این آلبوم یافت نشد.")
    else:
        await update.message.reply_text("سلام! خوش آمدید. برای ساخت آلبوم جدید از دکمه زیر استفاده کنید:", reply_markup=main_reply_menu())

# مدیریت پیام‌های ورودی و فایل‌ها
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message
    if not msg: return

    if msg.text == "📁 شروع ساخت آلبوم جدید":
        if user_id in last_bot_msg:
            try: await context.bot.delete_message(update.effective_chat.id, last_bot_msg[user_id])
            except: pass
        
        user_collections[user_id] = []
        keyboard = [
            [InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish')],
            [InlineKeyboardButton("❌ لغو", callback_data='cancel')]
        ]
        res = await msg.reply_text("🚀 حالت ساخت آلبوم فعال شد.\nفایل‌های خود را (عکس، ویدیو یا داکیومنت) بفرستید:", reply_markup=InlineKeyboardMarkup(keyboard))
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
            
            count = len(user_collections[user_id])
            keyboard = [[InlineKeyboardButton("✅ پایان و دریافت لینک", callback_data='finish')], [InlineKeyboardButton("❌ لغو", callback_data='cancel')]]
            res = await msg.reply_text(f"✅ فایل شماره {count} دریافت شد.\nمی‌توانید فایل بعدی را بفرستید یا روی پایان بزنید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
            last_bot_msg[user_id] = res.message_id

# مدیریت دکمه‌های شیشه‌ای
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'finish':
        if not user_collections.get(user_id):
            await query.message.reply_text("⚠️ شما هنوز فایلی ارسال نکرده‌اید!")
            return
        
        db = load_db()
        new_id = str(len(db) + 1001)
        db[new_id] = user_collections.pop(user_id)
        save_db(db)
        
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={new_id}"
        await query.edit_message_text(
            f"✅ آلبوم شما با موفقیت ساخته شد!\n📦 تعداد فایل‌ها: {len(db[new_id])}\n\n🔗 لینک تماشا:\n`{link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📤 اشتراک‌گذاری سریع", url=f"https://t.me/share/url?url={link}")]]),
            parse_mode='Markdown'
        )
        last_bot_msg.pop(user_id, None)

    elif query.data == 'cancel':
        user_collections.pop(user_id, None)
        await query.edit_message_text("❌ عملیات ساخت آلبوم لغو شد.")

# سیستم حذف خودکار
async def delete_after_delay(context, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for m_id in message_ids:
        try: await context.bot.delete_message(chat_id, m_id)
        except: pass

if __name__ == '__main__':
    # اجرای وب‌سرور در یک ترد جداگانه
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # راه‌اندازی ربات
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_messages))
    
    # شروع به کار ربات
    print("Bot is starting...")
    app.run_polling()
    
