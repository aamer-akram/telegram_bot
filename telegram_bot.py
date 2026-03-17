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
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
import io
import os
from dotenv import load_dotenv
import sqlite3
import datetime

# تحميل متغيرات البيئة
load_dotenv()

# إعداد التسجيل (logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالات المحادثة
AMOUNT, DAYS = range(2)

# تخزين بيانات المستخدمين مؤقتاً
user_data = {}

# ========== دوال قاعدة البيانات (SQLite) ==========

DB_FILE = 'bot_data.db'

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

def init_database():
    """إنشاء الجداول إذا لم تكن موجودة"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMP,
                last_active TIMESTAMP,
                total_operations INTEGER DEFAULT 0
            )
        ''')
        
        # جدول العمليات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                num_days INTEGER,
                result_data TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ قاعدة البيانات جاهزة")
        return True
    except Exception as e:
        logger.error(f"خطأ في إنشاء قاعدة البيانات: {e}")
        return False

def get_or_create_user(user_id, username, first_name, last_name=None):
    """الحصول على المستخدم أو إنشائه"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        now = datetime.datetime.now()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, now, now))
            logger.info(f"✅ مستخدم جديد: {first_name}")
        else:
            cursor.execute('''
                UPDATE users SET last_active = ?, username = ?, first_name = ?, last_name = ?
                WHERE user_id = ?
            ''', (now, username, first_name, last_name, user_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطأ في get_or_create_user: {e}")
        return False

def save_operation(user_id, amount, num_days, result_data=""):
    """حفظ عملية في السجل"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        now = datetime.datetime.now()
        
        cursor.execute('''
            INSERT INTO operations (user_id, amount, num_days, result_data, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, num_days, result_data, now))
        
        cursor.execute('''
            UPDATE users SET total_operations = total_operations + 1
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطأ في save_operation: {e}")
        return False

def get_user_operations(user_id, limit=10):
    """استرجاع آخر عمليات المستخدم"""
    try:
        conn = get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, num_days, created_at FROM operations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        operations = cursor.fetchall()
        conn.close()
        return operations
    except Exception as e:
        logger.error(f"خطأ في get_user_operations: {e}")
        return []

def get_bot_stats():
    """إحصائيات عامة عن البوت"""
    try:
        conn = get_db_connection()
        if not conn:
            return {
                'total_users': 0,
                'total_operations': 0,
                'active_today': 0
            }
        
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM operations")
        total_ops = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE last_active > datetime('now', '-1 day')
        ''')
        active_today = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_users': total_users,
            'total_operations': total_ops,
            'active_today': active_today
        }
    except Exception as e:
        logger.error(f"خطأ في get_bot_stats: {e}")
        return {
            'total_users': 0,
            'total_operations': 0,
            'active_today': 0
        }

# ========== دوال البوت الأساسية ==========

def reshape_arabic_text(text):
    """
    إعادة تشكيل النص العربي للعرض بشكل صحيح
    """
    if text and isinstance(text, str):
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    return text

def get_day_names(num_days):
    """
    الحصول على أسماء الأيام تبدأ من الأحد
    """
    all_days = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
    
    if num_days <= 7:
        return all_days[:num_days]
    else:
        days = []
        for i in range(num_days):
            day_index = i % 7
            days.append(all_days[day_index])
        return days

def create_schedule_table(amount, num_days):
    """
    إنشاء جدول تقسيم المقدار على عدد محدد من الأيام بطريقة دائرية
    مع تقريب القيم إلى أعلى رقم صحيح
    """
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
        first_start = starts[i]
        first_end = ends[i]
        first_period_values.append(f"{first_start}-{first_end}")
        
        second_index = (i + shift) % num_days
        second_start = starts[second_index]
        second_end = ends[second_index]
        second_period_values.append(f"{second_start}-{second_end}")
    
    data = {
        'الفترة الثانية': second_period_values,
        'الفترة الأولى': first_period_values,
        'اليوم': days
    }
    
    df = pd.DataFrame(data)
    
    logger.info(f"المقدار: {amount}, الأيام: {num_days}")
    logger.info(f"التوزيع: {list(zip(starts, ends))}")
    
    return df, amount, num_days

def create_table_image(df, amount, num_days):
    """
    إنشاء صورة ديناميكية للجدول مع ضمان أبعاد مناسبة لتليغرام
    """
    font_path = None
    windows_font_paths = [
        'C:/Windows/Fonts/Arial.ttf',
        'C:/Windows/Fonts/trado.ttf',
        'C:/Windows/Fonts/times.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        'C:/Windows/Fonts/Amiri.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    
    for path in windows_font_paths:
        try:
            if os.path.exists(path):
                font_path = path
                break
            elif fm.findfont(path):
                font_path = path
                break
        except:
            continue
    
    if not font_path:
        font_path = fm.findfont('Arial')
    
    if num_days <= 5:
        base_font_size = 20
    elif num_days <= 10:
        base_font_size = 16
    elif num_days <= 15:
        base_font_size = 14
    elif num_days <= 20:
        base_font_size = 12
    else:
        base_font_size = 10
    
    title_font_size = base_font_size + 10
    header_font_size = base_font_size + 10
    cell_font_size = base_font_size + 8
    footer_font_size = max(8, base_font_size - 2)
    
    pixels_per_row = cell_font_size * 2.5
    total_rows = 2 + num_days
    estimated_height_px = total_rows * pixels_per_row + 200
    max_allowed_height = 1200
    
    if estimated_height_px > max_allowed_height:
        reduction_factor = max_allowed_height / estimated_height_px
        base_font_size = max(8, int(base_font_size * reduction_factor))
        title_font_size = base_font_size + 4
        header_font_size = base_font_size + 2
        cell_font_size = base_font_size
        footer_font_size = max(8, base_font_size - 2)
        pixels_per_row = cell_font_size * 2.5
        estimated_height_px = total_rows * pixels_per_row + 200
    
    dpi = 100
    fig_height_inch = estimated_height_px / dpi
    fig_width_inch = 12
    max_height_inch = 12
    
    if fig_height_inch > max_height_inch:
        fig_height_inch = max_height_inch
    
    arabic_font = fm.FontProperties(fname=font_path, size=cell_font_size)
    header_font = fm.FontProperties(fname=font_path, size=header_font_size, weight='bold')
    title_font = fm.FontProperties(fname=font_path, size=title_font_size, weight='bold')
    footer_font = fm.FontProperties(fname=font_path, size=footer_font_size, style='italic')
    
    fig, ax = plt.subplots(figsize=(fig_width_inch, fig_height_inch))
    ax.axis('off')
    ax.axis('tight')
    
    header = [
        reshape_arabic_text('مساء'),
        reshape_arabic_text('صباح'),
        reshape_arabic_text('اليوم'),
        reshape_arabic_text('المقدار')
    ]
    
    amount_text = reshape_arabic_text(f'{amount}')
    amount_row = ['', '', '', amount_text]
    
    table_data = [header, amount_row]
    
    for index, row in df.iterrows():
        row_data = [
            reshape_arabic_text(row['الفترة الثانية']),
            reshape_arabic_text(row['الفترة الأولى']),
            reshape_arabic_text(row['اليوم']),
            ''
        ]
        table_data.append(row_data)
    
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', 
                     colWidths=[0.22, 0.22, 0.22, 0.22])
    
    table.auto_set_font_size(False)
    table.set_fontsize(cell_font_size)
    table.scale(1, 1.8)
    
    colors = {
        'header': '#2E86AB',
        'amount': '#F18F01',
        'day': '#A23B72',
        'row_even': '#F8F9FA',
        'row_odd': '#E9ECEF',
        'border': '#212529',
        'text_white': '#FFFFFF',
        'text_dark': '#212529'
    }
    
    for (i, j), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=arabic_font, ha='center', va='center')
        cell.set_edgecolor(colors['border'])
        cell.set_linewidth(1)
        
        if i == 0:
            cell.set_facecolor(colors['header'])
            cell.set_text_props(weight='bold', color=colors['text_white'], 
                              fontproperties=header_font)
            cell.set_height(0.15)
            
        elif i == 1:
            if j == 3:
                cell.set_facecolor(colors['amount'])
                cell.set_text_props(weight='bold', color=colors['text_dark'], 
                                  fontproperties=header_font)
                cell.set_height(0.12)
            else:
                cell.set_facecolor('#F0F0F0')
                cell.set_height(0.12)
                
        else:
            if i % 2 == 0:
                cell.set_facecolor(colors['row_even'])
            else:
                cell.set_facecolor(colors['row_odd'])
            
            cell.set_height(0.1)
                
            if j == 2:
                cell.set_facecolor(colors['day'])
                cell.set_text_props(weight='bold', color=colors['text_white'], 
                                  fontproperties=header_font)
            else:
                cell.set_text_props(color=colors['text_dark'])
    
    title_text = reshape_arabic_text(f' جدول تقسيم {amount} على {num_days} أيام')
    plt.suptitle(title_text, fontproperties=title_font, y=0.98)
    
    footer_text = reshape_arabic_text(' بوت تقسيم المقدار ')
    plt.figtext(0.5, 0.02, footer_text, fontproperties=footer_font, 
                ha='center', color='#6C757D')
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.92, bottom=0.05, left=0.03, right=0.97)
    
    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='PNG', dpi=100, bbox_inches='tight', 
                facecolor='white', edgecolor='none', pad_inches=0.2)
    plt.close()
    img_bytes.seek(0)
    
    return img_bytes

# ========== أوامر البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    بداية المحادثة - ترحيب وطلب المقدار
    """
    user = update.effective_user
    
    # تسجيل المستخدم في قاعدة البيانات
    get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_text = (
        f"👋 أهلاً {user.first_name}!\n\n"
        "🤖 *بوت تقسيم المقدار*\n"
        "هذا البوت يقوم بتقسيم أي رقم تدخله على عدد محدد من الأيام\n"
        "مع توزيع الفترات (صباحاً ومساءً) بشكل دائري\n\n"
        "/start - بدء محادثة جديدة\n"
        "/help - عرض المساعدة\n"
        "/profile - ملفك الشخصي\n"
        "/stats - إحصائيات البوت\n"
        "/cancel - إلغاء العملية\n\n"
        "🔹 *الرجاء إدخال المقدار:* \n"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return AMOUNT

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الملف الشخصي للمستخدم"""
    user = update.effective_user
    
    operations = get_user_operations(user.id, limit=5)
    stats = get_bot_stats()
    
    text = f"👤 *ملفك الشخصي*\n"
    text += f"🆔 المعرف: `{user.id}`\n"
    text += f"📝 الاسم: {user.first_name}\n"
    if user.username:
        text += f"🔗 اليوزرنيم: @{user.username}\n"
    
    text += f"\n📊 *إحصائيات البوت:*\n"
    text += f"👥 إجمالي المستخدمين: {stats['total_users']}\n"
    text += f"📈 إجمالي العمليات: {stats['total_operations']}\n"
    text += f"⭐ نشطون اليوم: {stats['active_today']}\n"
    
    if operations:
        text += f"\n📋 *آخر عملياتك:*\n"
        for i, op in enumerate(operations, 1):
            date_str = op['created_at'][:16] if isinstance(op['created_at'], str) else str(op['created_at'])[:16]
            text += f"{i}. `{op['amount']}` ÷ `{op['num_days']}` يوم 📅 {date_str}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات البوت"""
    stats = get_bot_stats()
    
    text = (
        f"📊 *إحصائيات البوت*\n\n"
        f"👥 **إجمالي المستخدمين:** `{stats['total_users']}`\n"
        f"📈 **إجمالي العمليات:** `{stats['total_operations']}`\n"
        f"⭐ **نشطون اليوم:** `{stats['active_today']}`\n\n"
        f"🗄️ *حالة قاعدة البيانات:* ✅ متصلة"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    عرض رسالة المساعدة
    """
    help_text = (
        "🤖 *بوت تقسيم المقدار - مساعدة*\n\n"
        "📌 *الأوامر المتاحة:*\n"
        "/start - بدء محادثة جديدة\n"
        "/help - عرض هذه المساعدة\n"
        "/profile - عرض ملفك الشخصي\n"
        "/stats - إحصائيات البوت\n"
        "/cancel - إلغاء العملية الحالية\n\n"
        "📝 *كيفية الاستخدام:*\n"
        "1️⃣ أرسل /start\n"
        "2️⃣ أدخل المقدار (مثال: 70)\n"
        "3️⃣ أدخل عدد الأيام (مثال: 7)\n"
        "4️⃣ استلم الجدول كصورة\n\n"
        "✅ *مميزات البوت:*\n"
        "• يدعم اللغة العربية بشكل كامل\n"
        "• الأيام تبدأ دائماً من الأحد\n"
        "• تقسيم دائري للفترات\n"
        "• تقريب الأرقام إلى أعلى قيمة\n"
        "• قاعدة بيانات SQLite لحفظ العمليات"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    إلغاء العملية الحالية
    """
    await update.message.reply_text(
        "❌ تم إلغاء العملية.\n"
        "لبدء عملية جديدة أرسل /start"
    )
    return ConversationHandler.END

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال المقدار من المستخدم
    """
    try:
        amount = float(update.message.text)
        
        if amount <= 0:
            await update.message.reply_text("❌ الرجاء إدخال مقدار أكبر من 0")
            return AMOUNT
        
        user_id = update.effective_user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['amount'] = amount
        
        await update.message.reply_text(
            f"✅ تم استلام المقدار: {amount}\n\n"
            "/cancel - إلغاء العملية الحالية\n\n"
            "🔹 *الرجاء إدخال عدد الأيام:*"
        )
        
        return DAYS
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return AMOUNT

async def get_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال عدد الأيام وإنشاء الجدول
    """
    try:
        num_days = int(update.message.text)
        user_id = update.effective_user.id
        
        if num_days <= 0:
            await update.message.reply_text("❌ الرجاء إدخال عدد أيام أكبر من 0")
            return DAYS
        
        amount = user_data[user_id]['amount']
        
        wait_msg = await update.message.reply_text("🔄 جاري إنشاء الجدول...")
        
        df, amount, num_days = create_schedule_table(amount, num_days)
        img_bytes = create_table_image(df, amount, num_days)
        
        # حفظ العملية في قاعدة البيانات
        save_operation(user_id, amount, num_days, f"تقسيم {amount} على {num_days}")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption=f"📊 *نتيجة تقسيم {amount} على {num_days} أيام*",
            parse_mode='Markdown'
        )
        
        await wait_msg.delete()
        
        await update.message.reply_text(
            "✅ *تمت العملية بنجاح!*\n"
            "لبدء عملية جديدة أرسل /start",
            parse_mode='Markdown'
        )
        
        del user_data[user_id]
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return DAYS
    except Exception as e:
        logger.error(f"حدث خطأ: {e}")
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    معالجة الأخطاء
    """
    logger.error(f"حدث خطأ: {context.error}")

def main():
    """
    الدالة الرئيسية لتشغيل البوت
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN")
        return
    
    # تهيئة قاعدة البيانات
    init_database()
    
    application = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('profile', profile))
    application.add_handler(CommandHandler('stats', stats))
    application.add_error_handler(error_handler)
    
    print("✅ البوت يعمل الآن... اضغط Ctrl+C للإيقاف")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0
    )

application = main

if __name__ == '__main__':
    main()