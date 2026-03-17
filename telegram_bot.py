import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import arabic_reshaper
from bidi.algorithm import get_display
import numpy as np
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler
)
import io
import os
from dotenv import load_dotenv

# استيراد دوال قاعدة البيانات
from database import (
    init_database, get_or_create_user, save_operation,
    get_user_operations, add_favorite, get_favorites,
    delete_favorite, get_bot_stats
)

# تحميل متغيرات البيئة
load_dotenv()

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== المتغيرات البيئية =====
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

if not TELEGRAM_TOKEN:
    logger.error("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN")

if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = None

# حالات المستخدمين (بدون ConversationHandler)
user_states = {}  # user_id: 'awaiting_amount' or 'awaiting_days'
user_amounts = {}  # user_id: amount

def reshape_arabic_text(text):
    if text and isinstance(text, str):
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    return text

def get_day_names(num_days):
    all_days = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
    if num_days <= 7:
        return all_days[:num_days]
    else:
        days = []
        for i in range(num_days):
            days.append(all_days[i % 7])
        return days

def create_schedule_table(amount, num_days):
    part_size = amount / num_days
    days = get_day_names(num_days)
    first_period_values = []
    second_period_values = []
    shift = num_days // 2
    
    starts = []
    ends = []
    
    for i in range(num_days):
        if i == 0:
            start = 1
        else:
            start = math.ceil(i * part_size) + 1
        
        if i == num_days - 1:
            end = int(amount)
        else:
            end = math.ceil((i + 1) * part_size)
        
        starts.append(start)
        ends.append(end)
    
    for i in range(1, num_days):
        if starts[i] > ends[i-1] + 1:
            starts[i] = ends[i-1] + 1
    
    for i in range(num_days):
        first_period_values.append(f"{starts[i]}-{ends[i]}")
        second_index = (i + shift) % num_days
        second_period_values.append(f"{starts[second_index]}-{ends[second_index]}")
    
    data = {
        'الفترة الثانية': second_period_values,
        'الفترة الأولى': first_period_values,
        'اليوم': days
    }
    
    return pd.DataFrame(data), amount, num_days

def create_table_image(df, amount, num_days):
    font_path = None
    windows_font_paths = [
        'C:/Windows/Fonts/Arial.ttf',
        'C:/Windows/Fonts/trado.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
    ]
    
    for path in windows_font_paths:
        if os.path.exists(path):
            font_path = path
            break
    
    if not font_path:
        font_path = fm.findfont('Arial')
    
    # حساب حجم الخط
    if num_days <= 5:
        base_size = 20
    elif num_days <= 10:
        base_size = 16
    elif num_days <= 15:
        base_size = 14
    else:
        base_size = 12
    
    cell_size = base_size
    header_size = base_size + 4
    title_size = base_size + 8
    
    # حساب ارتفاع الصورة
    fig_height = max(6, num_days * 0.5 + 3)
    fig, ax = plt.subplots(figsize=(12, fig_height))
    ax.axis('off')
    
    # تجهيز البيانات
    header = [
        reshape_arabic_text('مساء'),
        reshape_arabic_text('صباح'),
        reshape_arabic_text('اليوم'),
        reshape_arabic_text('المقدار')
    ]
    
    amount_row = ['', '', '', reshape_arabic_text(f'{amount}')]
    table_data = [header, amount_row]
    
    for _, row in df.iterrows():
        table_data.append([
            reshape_arabic_text(row['الفترة الثانية']),
            reshape_arabic_text(row['الفترة الأولى']),
            reshape_arabic_text(row['اليوم']),
            ''
        ])
    
    # إنشاء الجدول
    table = ax.table(cellText=table_data, loc='center', cellLoc='center',
                     colWidths=[0.22, 0.22, 0.22, 0.22])
    
    table.auto_set_font_size(False)
    table.set_fontsize(cell_size)
    table.scale(1, 1.8)
    
    # تنسيق الألوان
    colors = {
        'header': '#2E86AB', 'amount': '#F18F01', 'day': '#A23B72',
        'row_even': '#F8F9FA', 'row_odd': '#E9ECEF', 'border': '#212529'
    }
    
    for (i, j), cell in table.get_celld().items():
        cell.set_edgecolor(colors['border'])
        cell.set_linewidth(1)
        cell.set_text_pros(fontproperties=fm.FontProperties(fname=font_path, size=cell_size), ha='center')
        
        if i == 0:
            cell.set_facecolor(colors['header'])
            cell.set_text_props(weight='bold', color='white')
        elif i == 1 and j == 3:
            cell.set_facecolor(colors['amount'])
            cell.set_text_props(weight='bold')
        elif j == 2 and i > 1:
            cell.set_facecolor(colors['day'])
            cell.set_text_props(weight='bold', color='white')
        else:
            cell.set_facecolor(colors['row_even'] if i % 2 == 0 else colors['row_odd'])
    
    # عنوان
    plt.suptitle(reshape_arabic_text(f'جدول تقسيم {amount} على {num_days} أيام'),
                 fontproperties=fm.FontProperties(fname=font_path, size=title_size, weight='bold'),
                 y=0.98)
    
    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='PNG', dpi=100, bbox_inches='tight', facecolor='white')
    plt.close()
    img_bytes.seek(0)
    
    return img_bytes

# ========== المعالجات ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بداية المحادثة"""
    user = update.effective_user
    user_states[user.id] = 'awaiting_amount'
    
    await update.message.reply_text(
        f"👋 أهلاً {user.first_name}!\n\n"
        "🤖 *بوت تقسيم المقدار*\n\n"
        "🔹 *الرجاء إدخال المقدار:*",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مساعدة"""
    await update.message.reply_text(
        "🤖 *بوت تقسيم المقدار - مساعدة*\n\n"
        "/start - بدء محادثة جديدة\n"
        "/profile - ملفك الشخصي\n"
        "/list_fav - المفضلة\n"
        "/save_fav - حفظ آخر عملية\n"
        "/cancel - إلغاء",
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء"""
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_amounts:
        del user_amounts[user_id]
    await update.message.reply_text("✅ تم الإلغاء. أرسل /start لبداية جديدة")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الملف الشخصي"""
    user = update.effective_user
    ops = get_user_operations(user.id, limit=5)
    favs = get_favorites(user.id)
    
    text = f"👤 *{user.first_name}*\n🆔 `{user.id}`\n"
    if ops:
        text += "\n📋 *آخر العمليات:*\n"
        for i, op in enumerate(ops[:3], 1):
            text += f"{i}. {op['amount']} ÷ {op['num_days']}\n"
    if favs:
        text += f"\n⭐ *المفضلة:* {len(favs)} عناصر\n/list_fav للعرض"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def save_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ في المفضلة"""
    user_id = update.effective_user.id
    ops = get_user_operations(user_id, limit=1)
    
    if not ops:
        await update.message.reply_text("❌ لا توجد عمليات سابقة")
        return
    
    name = " ".join(context.args) if context.args else f"عملية {ops[0]['amount']} ÷ {ops[0]['num_days']}"
    fav_id = add_favorite(user_id, name, ops[0]['amount'], ops[0]['num_days'])
    
    if fav_id:
        await update.message.reply_text(f"✅ تم الحفظ برقم `{fav_id}`", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ فشل الحفظ")

async def list_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المفضلة"""
    user_id = update.effective_user.id
    favs = get_favorites(user_id)
    
    if not favs:
        await update.message.reply_text("📭 المفضلة فارغة")
        return
    
    text = "⭐ *مفضلتك*\n\n"
    for fav in favs:
        text += f"`{fav['id']}`: {fav['name']} ({fav['amount']}÷{fav['num_days']})\n"
    text += "\nاستخدم /use_fav رقم"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def use_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام عنصر من المفضلة"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("❌ استخدم: /use_fav رقم")
        return
    
    try:
        fav_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ رقم غير صحيح")
        return
    
    favs = get_favorites(user_id)
    selected = next((f for f in favs if f['id'] == fav_id), None)
    
    if not selected:
        await update.message.reply_text("❌ عنصر غير موجود")
        return
    
    wait = await update.message.reply_text("🔄 جاري الإنشاء...")
    df, _, _ = create_schedule_table(selected['amount'], selected['num_days'])
    img = create_table_image(df, selected['amount'], selected['num_days'])
    
    await update.message.reply_photo(photo=img, caption=f"📊 *{selected['name']}*", parse_mode='Markdown')
    await wait.delete()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات"""
    if not ADMIN_ID or update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ غير مصرح")
        return
    
    s = get_bot_stats()
    await update.message.reply_text(
        f"📊 *الإحصائيات*\n\n👥 المستخدمين: {s['total_users']}\n📈 العمليات: {s['total_operations']}\n⭐ نشاط اليوم: {s['active_today']}",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # التحقق من الحالة
    state = user_states.get(user_id)
    
    if state == 'awaiting_amount':
        # استقبال المقدار
        try:
            amount = float(text)
            if amount <= 0:
                await update.message.reply_text("❌ الرجاء إدخال رقم موجب")
                return
            
            user_amounts[user_id] = amount
            user_states[user_id] = 'awaiting_days'
            await update.message.reply_text(f"✅ تم استلام {amount}\n\n🔹 الآن أدخل عدد الأيام:")
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
    
    elif state == 'awaiting_days':
        # استقبال عدد الأيام وإنشاء الجدول
        try:
            days = int(text)
            if days <= 0:
                await update.message.reply_text("❌ الرجاء إدخال عدد أيام موجب")
                return
            
            amount = user_amounts.get(user_id)
            if not amount:
                user_states[user_id] = 'awaiting_amount'
                await update.message.reply_text("❌ خطأ، أعد إدخال المقدار")
                return
            
            wait = await update.message.reply_text("🔄 جاري إنشاء الجدول...")
            
            # إنشاء الجدول
            df, amount, days = create_schedule_table(amount, days)
            img = create_table_image(df, amount, days)
            
            # حفظ في قاعدة البيانات
            get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
            save_operation(user_id, amount, days)
            
            # إرسال الصورة
            keyboard = [[InlineKeyboardButton("⭐ حفظ في المفضلة", callback_data=f"save_{amount}_{days}")]]
            await update.message.reply_photo(
                photo=img,
                caption=f"📊 *نتيجة تقسيم {amount} على {days} أيام*",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            await wait.delete()
            
            # إنهاء المحادثة
            del user_states[user_id]
            del user_amounts[user_id]
            
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال عدد صحيح")
    else:
        # إذا لم يكن في محادثة
        await update.message.reply_text("أرسل /start لبدء محادثة جديدة")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('save_'):
        # حفظ في المفضلة
        _, amount, days = query.data.split('_')
        user_id = query.from_user.id
        
        name = f"عملية {amount} ÷ {days}"
        fav_id = add_favorite(user_id, name, float(amount), int(days))
        
        if fav_id:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"✅ تم الحفظ في المفضلة برقم `{fav_id}`", parse_mode='Markdown')
        else:
            await query.message.reply_text("❌ فشل الحفظ")

def main():
    """تشغيل البوت"""
    if not TELEGRAM_TOKEN:
        print("❌ لا يوجد توكن")
        return
    
    # تهيئة قاعدة البيانات
    init_database()
    
    # إنشاء التطبيق
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('cancel', cancel))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('stats', stats))
    app.add_handler(CommandHandler('save_fav', save_fav))
    app.add_handler(CommandHandler('list_fav', list_fav))
    app.add_handler(CommandHandler('use_fav', use_fav))
    
    # معالج الرسائل النصية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # معالج الأزرار
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # تشغيل البوت
    print("✅ البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()