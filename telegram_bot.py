import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import arabic_reshaper
from bidi.algorithm import get_display
import numpy as np
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import io
import os
from dotenv import load_dotenv

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
    
    المعاملات:
    num_days: عدد الأيام المطلوبة
    """
    # قائمة أيام الأسبوع كاملة
    all_days = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
    
    if num_days <= 7:
        # إذا كان عدد الأيام 7 أو أقل، نأخذ أول num_days أيام
        return all_days[:num_days]
    else:
        # إذا كان عدد الأيام أكثر من 7، نكرر الأيام بشكل دوري
        days = []
        for i in range(num_days):
            day_index = i % 7
            days.append(all_days[day_index])
        return days

def create_schedule_table(amount, num_days):
    """
    إنشاء جدول تقسيم المقدار على عدد محدد من الأيام بطريقة دائرية
    
    المعاملات:
    amount: المقدار المراد تقسيمه
    num_days: عدد الأيام
    """
    
    # حساب قيمة الجزء الواحد (المقدار مقسوم على عدد الأيام)
    part_size = amount / num_days
    
    # الحصول على أسماء الأيام (تبدأ من الأحد)
    days = get_day_names(num_days)
    
    # حساب قيم الفترة الأولى والثانية لكل يوم
    first_period_values = []
    second_period_values = []
    
    # حساب الإزاحة للنمط الدائري (نصف عدد الأيام تقريباً)
    shift = num_days // 2
    
    for i in range(num_days):
        # حساب قيم الفترة الأولى
        first_start = int(i * part_size) + 1
        first_end = int((i + 1) * part_size)
        
        # التأكد من أن القيم ضمن النطاق الصحيح
        if i == num_days - 1:  # اليوم الأخير
            first_end = int(amount)
        
        # حساب قيم الفترة الثانية (مع إزاحة دائرية)
        second_index = (i + shift) % num_days
        
        second_start = int(second_index * part_size) + 1
        second_end = int((second_index + 1) * part_size)
        
        if second_index == num_days - 1:  # إذا كان اليوم الأخير
            second_end = int(amount)
        
        # تنسيق القيم كسلاسل نصية
        first_period_values.append(f"{first_start}-{first_end}")
        second_period_values.append(f"{second_start}-{second_end}")
    
    # إنشاء DataFrame للجدول (مع ترتيب عكسي للأعمدة)
    data = {
        'الفترة الثانية': second_period_values,
        'الفترة الأولى': first_period_values,
        'اليوم': days
    }
    
    df = pd.DataFrame(data)
    
    return df, amount, num_days

def create_table_image(df, amount, num_days):
    """
    إنشاء صورة للجدول مع دعم اللغة العربية وعكس الاتجاه
    وإرجاعها كـ BytesIO
    """
    
    # البحث عن خط يدعم اللغة العربية
    font_path = None
    windows_font_paths = [
        'C:/Windows/Fonts/Arial.ttf',
        'C:/Windows/Fonts/trado.ttf',
        'C:/Windows/Fonts/times.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        'C:/Windows/Fonts/Amiri.ttf'
    ]
    
    for path in windows_font_paths:
        try:
            if fm.findfont(path):
                font_path = path
                break
        except:
            continue
    
    if not font_path:
        font_path = fm.findfont('Arial')
    
    # إعداد الخط للغة العربية
    arabic_font = fm.FontProperties(fname=font_path, size=12)
    title_font = fm.FontProperties(fname=font_path, size=16, weight='bold')
    
    # تحديد حجم الشكل بناءً على عدد الأيام
    fig_height = max(7, num_days * 0.5 + 3)
    fig, ax = plt.subplots(figsize=(14, fig_height))
    ax.axis('off')
    ax.axis('tight')
    
    # تجهيز البيانات مع إعادة تشكيل النص العربي (بترتيب عكسي)
    header = [
        reshape_arabic_text('الفترة الثانية'),
        reshape_arabic_text('الفترة الأولى'),
        reshape_arabic_text('اليوم'),
        reshape_arabic_text('المقدار')
    ]
    
    # صف المقدار
    amount_text = reshape_arabic_text(f'{amount}')
    amount_row = ['', '', '', amount_text]
    
    # تجهيز جميع الصفوف
    table_data = [header, amount_row]
    
    # إضافة بيانات الأيام
    for index, row in df.iterrows():
        row_data = [
            reshape_arabic_text(row['الفترة الثانية']),
            reshape_arabic_text(row['الفترة الأولى']),
            reshape_arabic_text(row['اليوم']),
            ''
        ]
        table_data.append(row_data)
    
    # إنشاء الجدول
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', 
                     colWidths=[0.25, 0.25, 0.2, 0.2])
    
    # تنسيق الجدول
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 1.5)
    
    # تنسيق الخلايا
    for (i, j), cell in table.get_celld().items():
        cell.set_text_props(fontproperties=arabic_font, ha='center')
        
        if i == 0:  # صف العنوان
            cell.set_facecolor('#4CAF50')
            cell.set_text_props(weight='bold', color='white', 
                              fontproperties=arabic_font, ha='center')
        elif i == 1:  # صف المقدار
            if j == 3:  # عمود المقدار
                cell.set_facecolor('#FFA500')
                cell.set_text_props(weight='bold', fontproperties=arabic_font, ha='center')
            else:
                cell.set_facecolor('#f0f0f0')
        else:  # باقي الصفوف
            if j == 2:  # عمود اليوم
                cell.set_facecolor('#E3F2FD')
                cell.set_text_props(weight='bold', fontproperties=arabic_font, ha='center')
            else:
                cell.set_facecolor('#F5F5F5')
        
        cell.set_edgecolor('#333333')
        cell.set_linewidth(1)
    
    # إضافة عنوان للجدول
    title_text = reshape_arabic_text(f'جدول تقسيم المقدار ({amount}) على {num_days} أيام')
    plt.suptitle(title_text, fontproperties=title_font, y=0.95)
    
    # حفظ الصورة في الذاكرة
    img_bytes = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img_bytes, format='PNG', dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    img_bytes.seek(0)
    
    return img_bytes

def format_table_text(df, amount, num_days):
    """
    تنسيق الجدول كنص لإرساله عبر تيليغرام
    """
    text = f"📊 *جدول تقسيم المقدار ({amount}) على {num_days} أيام*\n"
    text += "=" * 40 + "\n\n"
    
    # رؤوس الأعمدة
    text += "`"
    text += f"{'اليوم':<15} {'الفترة الأولى':<15} {'الفترة الثانية':<15}\n"
    text += "-" * 45 + "\n"
    
    # البيانات
    for index, row in df.iterrows():
        text += f"{row['اليوم']:<15} {row['الفترة الأولى']:<15} {row['الفترة الثانية']:<15}\n"
    
    text += "`\n\n"
    
    # تفاصيل إضافية
    part_size = amount / num_days
    text += "📝 *تفاصيل التقسيم:*\n"
    text += f"• قيمة الجزء الواحد: `{part_size:.2f}`\n"
    text += f"• عدد الأيام: `{num_days}`\n"
    text += f"• أول يوم: الأحد\n"
    text += f"• نمط التوزيع: دائري (إزاحة {num_days // 2} أيام)\n"
    
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    بداية المحادثة - ترحيب وطلب المقدار
    """
    user = update.effective_user
    welcome_text = (
        f"👋 أهلاً {user.first_name}!\n\n"
        "🤖 *بوت تقسيم المقدار*\n"
        "هذا البوت يقوم بتقسيم أي رقم تدخله على عدد محدد من الأيام\n"
        "مع توزيع الفترات (صباحاً ومساءً) بشكل دائري\n\n"
        "🔹 *الرجاء إدخال المقدار:*"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return AMOUNT

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    عرض رسالة المساعدة
    """
    help_text = (
        "🤖 *بوت تقسيم المقدار - مساعدة*\n\n"
        "📌 *الأوامر المتاحة:*\n"
        "/start - بدء محادثة جديدة\n"
        "/help - عرض هذه المساعدة\n"
        "/cancel - إلغاء العملية الحالية\n\n"
        "📝 *كيفية الاستخدام:*\n"
        "1️⃣ أرسل /start\n"
        "2️⃣ أدخل المقدار (مثال: 150)\n"
        "3️⃣ أدخل عدد الأيام (مثال: 7)\n"
        "4️⃣ استلم الجدول كصورة ونص\n\n"
        "✅ *مميزات البوت:*\n"
        "• يدعم اللغة العربية بشكل كامل\n"
        "• الأيام تبدأ دائماً من الأحد\n"
        "• تقسيم دائري للفترات\n"
        "• إرسال النتيجة كصورة ونص"
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
        
        # تخزين المقدار في بيانات المستخدم
        user_id = update.effective_user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['amount'] = amount
        
        # طلب عدد الأيام
        await update.message.reply_text(
            f"✅ تم استلام المقدار: {amount}\n\n"
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
        
        # استرجاع المقدار
        amount = user_data[user_id]['amount']
        
        # إرسال رسالة انتظار
        wait_msg = await update.message.reply_text("🔄 جاري إنشاء الجدول...")
        
        # إنشاء الجدول
        df, amount, num_days = create_schedule_table(amount, num_days)
        
        # إنشاء صورة الجدول
        img_bytes = create_table_image(df, amount, num_days)
        
        # تنسيق النص
        text_result = format_table_text(df, amount, num_days)
        
        # إرسال الصورة
        await update.message.reply_photo(
            photo=img_bytes,
            caption="📸 *صورة الجدول*",
            parse_mode='Markdown'
        )
        
        # إرسال النص
        await update.message.reply_text(
            text_result,
            parse_mode='Markdown'
        )
        
        # حذف رسالة الانتظار
        await wait_msg.delete()
        
        # رسالة نجاح
        await update.message.reply_text(
            "✅ *تمت العملية بنجاح!*\n"
            "لبدء عملية جديدة أرسل /start",
            parse_mode='Markdown'
        )
        
        # تنظيف بيانات المستخدم
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
    # الحصول على التوكن من متغيرات البيئة
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN في ملف .env")
        print("📝 الرجاء إنشاء ملف .env وإضافة التوكن الخاص بك")
        return
    
    # إنشاء التطبيق
    application = Application.builder().token(token).build()
    
    # إضافة معالج المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False  # مهم للمحادثات الطويلة
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    
    # إضافة معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    print("✅ البوت يعمل الآن... اضغط Ctrl+C للإيقاف")
    application.run_polling(allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # مهم: يتجاهل أي تحديثات قديمة
        poll_interval=1.0  # التحقق من الرسائل كل ثانية
        )
# للاستخدام مع Render - هذا هو المتغير الذي يبحث عنه Render
application = main

if __name__ == '__main__':
    main()
