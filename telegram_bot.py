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

# استيراد دوال قاعدة البيانات
from database import (
    init_database, get_or_create_user, save_operation,
    get_user_operations, add_favorite, get_favorites,
    delete_favorite, get_bot_stats
)

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

# تخزين بيانات المستخدمين مؤقتاً (للمحادثات النشطة فقط)
user_data = {}

# ===== المتغيرات البيئية =====
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')

# التحقق من المتغيرات البيئية
if not TELEGRAM_TOKEN:
    logger.error("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في المتغيرات البيئية")

if not ADMIN_ID:
    logger.warning("⚠️ لم يتم العثور على ADMIN_ID في المتغيرات البيئية. أوامر المسؤول لن تعمل.")
else:
    try:
        ADMIN_ID = int(ADMIN_ID)
        logger.info(f"✅ تم تحميل ADMIN_ID: {ADMIN_ID}")
    except ValueError:
        logger.error("❌ ADMIN_ID يجب أن يكون رقماً صحيحاً")
        ADMIN_ID = None

def reshape_arabic_text(text):
    """إعادة تشكيل النص العربي للعرض بشكل صحيح"""
    if text and isinstance(text, str):
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    return text

def get_day_names(num_days):
    """الحصول على أسماء الأيام تبدأ من الأحد"""
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
    """إنشاء جدول تقسيم المقدار على عدد محدد من الأيام بطريقة دائرية"""
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
    return df, amount, num_days

def create_table_image(df, amount, num_days):
    """إنشاء صورة ديناميكية للجدول مع ضمان أبعاد مناسبة لتليغرام"""
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

# ========== أوامر قاعدة البيانات ==========

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملف المستخدم وإحصائياته من قاعدة البيانات"""
    user = update.effective_user
    
    get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    operations = get_user_operations(user.id, limit=5)
    favorites = get_favorites(user.id)
    
    text = f"👤 *ملفك الشخصي*\n"
    text += f"🆔 المعرف: `{user.id}`\n"
    text += f"📝 الاسم: {user.first_name}\n"
    if user.username:
        text += f"🔗 اليوزرنيم: @{user.username}\n"
    
    stats = get_bot_stats()
    text += f"\n📊 *إحصائيات سريعة:*\n"
    text += f"👥 إجمالي المستخدمين: {stats['total_users']}\n"
    text += f"📈 إجمالي العمليات: {stats['total_operations']}\n"
    
    if operations:
        text += f"\n📋 *آخر {len(operations)} عملياتك:*\n"
        for i, op in enumerate(operations, 1):
            date_str = op['created_at'].strftime("%Y-%m-%d %H:%M") if hasattr(op['created_at'], 'strftime') else str(op['created_at'])[:16]
            text += f"{i}. `{op['amount']}` ÷ `{op['num_days']}` يوم 📅 {date_str}\n"
    else:
        text += f"\n📭 لا توجد عمليات سابقة\n"
    
    if favorites:
        text += f"\n⭐ *مفضلتك ({len(favorites)}):*\n"
        for fav in favorites[:3]:
            text += f"🔹 {fav['name']}: `{fav['amount']}` ÷ `{fav['num_days']}`\n"
        if len(favorites) > 3:
            text += f"...و {len(favorites)-3} عناصر أخرى. استخدم /list_fav لعرض الكل\n"
    else:
        text += f"\n⭐ لا توجد مفضلة. استخدم /save_fav لحفظ عملية\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات البوت (للمسؤول فقط)"""
    if not ADMIN_ID:
        await update.message.reply_text("❌ لم يتم تعيين معرف المسؤول")
        return
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذه الميزة للمسؤول فقط")
        return
    
    stats = get_bot_stats()
    
    text = (
        f"📊 *إحصائيات البوت*\n\n"
        f"👥 **إجمالي المستخدمين:** `{stats['total_users']}`\n"
        f"📈 **إجمالي العمليات:** `{stats['total_operations']}`\n"
        f"🔄 **مجموع العمليات:** `{stats['operations_sum']}`\n"
        f"⭐ **نشطون اليوم:** `{stats['active_today']}`\n\n"
        f"🗄️ *حالة قاعدة البيانات:* ✅ متصلة\n\n"
        f"🆔 *معرف المسؤول:* `{ADMIN_ID}`"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def save_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ العملية الأخيرة في المفضلة"""
    user_id = update.effective_user.id
    
    operations = get_user_operations(user_id, limit=1)
    if not operations:
        await update.message.reply_text(
            "❌ لا توجد عمليات سابقة للحفظ\n"
            "قم بتقسيم رقم أولاً ثم استخدم هذا الأمر"
        )
        return
    
    last_op = operations[0]
    
    custom_name = " ".join(context.args) if context.args else None
    if custom_name:
        name = custom_name
    else:
        name = f"عملية {last_op['amount']} ÷ {last_op['num_days']}"
    
    fav_id = add_favorite(user_id, name, last_op['amount'], last_op['num_days'])
    
    if fav_id:
        keyboard = [
            [InlineKeyboardButton("📋 عرض المفضلة", callback_data='list_fav')],
            [InlineKeyboardButton("➕ حفظ عملية أخرى", callback_data='save_fav')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ **تم حفظ العملية في المفضلة!**\n"
            f"🆔 رقم العنصر: `{fav_id}`\n"
            f"📝 الاسم: {name}\n"
            f"📊 المقدار: `{last_op['amount']}`\n"
            f"📅 الأيام: `{last_op['num_days']}`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ حدث خطأ في الحفظ")

async def list_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المفضلة كاملة مع أزرار تفاعلية"""
    user_id = update.effective_user.id
    favorites = get_favorites(user_id)
    
    if not favorites:
        await update.message.reply_text(
            "📭 **لا توجد عناصر في المفضلة**\n\n"
            "💡 استخدم /save_fav لحفظ عملية حالية\n"
            "أو قم بتقسيم رقم ثم احفظه",
            parse_mode='Markdown'
        )
        return
    
    keyboard = []
    for fav in favorites:
        button_text = f"{fav['name']} ({fav['amount']} ÷ {fav['num_days']})"
        callback_data = f"use_fav_{fav['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([
        InlineKeyboardButton("➕ حفظ جديد", callback_data='save_fav'),
        InlineKeyboardButton("🗑️ مسح الكل", callback_data='clear_fav')
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⭐ **مفضلتك** ({len(favorites)} عناصر)\n\n"
        f"اختر عنصراً لاستخدامه:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def use_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استخدام عنصر من المفضلة"""
    user_id = update.effective_user.id
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        fav_id = int(query.data.split('_')[2])
        
        favorites = get_favorites(user_id)
        selected = None
        for fav in favorites:
            if fav['id'] == fav_id:
                selected = fav
                break
        
        if not selected:
            await query.edit_message_text("❌ لم يتم العثور على العنصر")
            return
        
        await query.edit_message_text(f"🔄 جاري تحميل '{selected['name']}'...")
        
        amount = selected['amount']
        num_days = selected['num_days']
        
        df, _, _ = create_schedule_table(amount, num_days)
        img_bytes = create_table_image(df, amount, num_days)
        
        await context.bot.send_photo(
            chat_id=user_id,
            photo=img_bytes,
            caption=f"📊 *{selected['name']}*",
            parse_mode='Markdown'
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ تم التقسيم بنجاح!\nلاستخدام عنصر آخر: /list_fav",
            parse_mode='Markdown'
        )
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ استخدم: `/use_fav رقم_المفضلة`\n"
                "لعرض قائمة المفضلة: /list_fav",
                parse_mode='Markdown'
            )
            return
        
        fav_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return
    
    favorites = get_favorites(user_id)
    
    selected = None
    for fav in favorites:
        if fav['id'] == fav_id:
            selected = fav
            break
    
    if not selected:
        await update.message.reply_text("❌ لم يتم العثور على العنصر")
        return
    
    amount = selected['amount']
    num_days = selected['num_days']
    
    wait_msg = await update.message.reply_text(f"🔄 جاري تحميل '{selected['name']}'...")
    
    df, _, _ = create_schedule_table(amount, num_days)
    img_bytes = create_table_image(df, amount, num_days)
    
    await update.message.reply_photo(
        photo=img_bytes,
        caption=f"📊 *{selected['name']}*\nالنتيجة: {amount} ÷ {num_days} أيام",
        parse_mode='Markdown'
    )
    
    await wait_msg.delete()

async def clear_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسح كل عناصر المفضلة"""
    user_id = update.effective_user.id
    favorites = get_favorites(user_id)
    
    if not favorites:
        await update.message.reply_text("📭 لا توجد عناصر في المفضلة")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ نعم، امسح الكل", callback_data='confirm_clear'),
            InlineKeyboardButton("❌ لا، تراجع", callback_data='cancel_clear')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚠️ **تأكيد المسح**\n\n"
        f"هل أنت متأكد من مسح جميع عناصر المفضلة ({len(favorites)} عناصر)؟",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار التفاعلية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == 'list_fav':
        favorites = get_favorites(user_id)
        if not favorites:
            await query.edit_message_text("📭 لا توجد عناصر في المفضلة")
            return
        
        keyboard = []
        for fav in favorites:
            button_text = f"{fav['name']} ({fav['amount']} ÷ {fav['num_days']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"use_fav_{fav['id']}")])
        
        keyboard.append([InlineKeyboardButton("➕ حفظ جديد", callback_data='save_fav')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⭐ **مفضلتك** ({len(favorites)} عناصر)",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == 'save_fav':
        await query.edit_message_text(
            "📝 **لحفظ عملية في المفضلة:**\n\n"
            "1️⃣ قم بتقسيم رقم أولاً\n"
            "2️⃣ ثم أرسل: `/save_fav اسم_مخصص`\n\n"
            "مثال: `/save_fav راتبي الشهري`",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('use_fav_'):
        fav_id = int(query.data.split('_')[2])
        favorites = get_favorites(user_id)
        
        selected = None
        for fav in favorites:
            if fav['id'] == fav_id:
                selected = fav
                break
        
        if not selected:
            await query.edit_message_text("❌ لم يتم العثور على العنصر")
            return
        
        await query.edit_message_text(f"🔄 جاري تحميل '{selected['name']}'...")
        
        amount = selected['amount']
        num_days = selected['num_days']
        
        df, _, _ = create_schedule_table(amount, num_days)
        img_bytes = create_table_image(df, amount, num_days)
        
        await context.bot.send_photo(
            chat_id=user_id,
            photo=img_bytes,
            caption=f"📊 *{selected['name']}*",
            parse_mode='Markdown'
        )
    
    elif query.data == 'confirm_clear':
        favorites = get_favorites(user_id)
        for fav in favorites:
            delete_favorite(fav['id'], user_id)
        
        await query.edit_message_text("✅ **تم مسح جميع عناصر المفضلة**", parse_mode='Markdown')
    
    elif query.data == 'cancel_clear':
        await query.edit_message_text("✅ تم إلغاء المسح", parse_mode='Markdown')

# ========== الأوامر الأساسية ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    بداية المحادثة - ترحيب وطلب المقدار
    """
    user = update.effective_user
    logger.info(f"مستخدم جديد: {user.first_name} (ID: {user.id})")
    
    # حفظ المستخدم في قاعدة البيانات
    try:
        get_or_create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    except Exception as e:
        logger.error(f"خطأ في حفظ المستخدم: {e}")
    
    welcome_text = (
        f"👋 أهلاً {user.first_name}!\n\n"
        "🤖 *بوت تقسيم المقدار*\n"
        "هذا البوت يقوم بتقسيم أي رقم تدخله على عدد محدد من الأيام\n"
        "مع توزيع الفترات (صباحاً ومساءً) بشكل دائري\n\n"
        "📌 *الأوامر المتاحة:*\n"
        "/start - بدء محادثة جديدة\n"
        "/help - عرض المساعدة\n"
        "/profile - ملفك الشخصي\n"
        "/list_fav - عرض المفضلة\n"
        "/cancel - إلغاء العملية\n\n"
        "🔹 *الرجاء إدخال المقدار:*"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return AMOUNT

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض رسالة المساعدة"""
    help_text = (
        "🤖 *بوت تقسيم المقدار - مساعدة*\n\n"
        "📌 *الأوامر المتاحة:*\n"
        "┌ /start - بدء محادثة جديدة\n"
        "├ /help - عرض هذه المساعدة\n"
        "├ /profile - عرض ملفك الشخصي\n"
        "├ /list_fav - عرض قائمة المفضلة\n"
        "├ /save_fav [اسم] - حفظ آخر عملية\n"
        "├ /use_fav [رقم] - استخدام عنصر من المفضلة\n"
        "├ /stats - إحصائيات (للمسؤول)\n"
        "└ /cancel - إلغاء العملية\n\n"
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
        "• قاعدة بيانات لحفظ العمليات"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء العملية الحالية"""
    await update.message.reply_text(
        "❌ تم إلغاء العملية.\n"
        "لبدء عملية جديدة أرسل /start"
    )
    return ConversationHandler.END

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المقدار من المستخدم"""
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
    """استقبال عدد الأيام وإنشاء الجدول"""
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
        save_operation(user_id, amount, num_days, f"تقسيم {amount} على {num_days} أيام")
        
        await update.message.reply_photo(
            photo=img_bytes,
            caption=f"📊 *نتيجة تقسيم {amount} على {num_days} أيام*",
            parse_mode='Markdown'
        )
        
        # اقتراح حفظ في المفضلة
        keyboard = [
            [InlineKeyboardButton("⭐ حفظ في المفضلة", callback_data='save_fav')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await wait_msg.delete()
        
        await update.message.reply_text(
            "✅ *تمت العملية بنجاح!*\n"
            "لبدء عملية جديدة أرسل /start",
            parse_mode='Markdown',
            reply_markup=reply_markup
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
    """معالجة الأخطاء"""
    logger.error(f"حدث خطأ: {context.error}")

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    if not TELEGRAM_TOKEN:
        print("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN في المتغيرات البيئية")
        return
    
    # تهيئة قاعدة البيانات
    print("🔄 جاري تهيئة قاعدة البيانات...")
    try:
        if init_database():
            print("✅ قاعدة البيانات جاهزة")
        else:
            print("⚠️ تحذير: فشل الاتصال بقاعدة البيانات، سيستمر البوت بدون حفظ بيانات")
    except Exception as e:
        print(f"⚠️ خطأ في قاعدة البيانات: {e}")
    
    # إنشاء التطبيق
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # معالج اختباري للتأكد من عمل البوت
    async def test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("✅ البوت يعمل بشكل طبيعي!")
    
    application.add_handler(CommandHandler('test', test_handler))
    
    # إضافة معالج المحادثة (للأمر start)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        name="main_conversation"
    )
    
    application.add_handler(conv_handler)
    
    # إضافة الأوامر الأخرى
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('profile', profile))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('save_fav', save_favorite))
    application.add_handler(CommandHandler('list_fav', list_favorites))
    application.add_handler(CommandHandler('use_fav', use_favorite))
    application.add_handler(CommandHandler('clear_fav', clear_favorites))
    
    # إضافة معالج الأزرار التفاعلية
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # إضافة معالج للأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    print("✅ البوت يعمل الآن... اضغط Ctrl+C للإيقاف")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0
    )

# للاستخدام مع Railway/Render
application = main

if __name__ == '__main__':
    main()