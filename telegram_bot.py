import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import arabic_reshaper
from bidi.algorithm import get_display
import numpy as np
import logging
from telegram import Update
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
    
    # حساب قيمة الجزء الواحد
    part_size = amount / num_days
    
    # الحصول على أسماء الأيام
    days = get_day_names(num_days)
    
    # حساب قيم الفترة الأولى والثانية
    first_period_values = []
    second_period_values = []
    
    # حساب الإزاحة للنمط الدائري (نصف عدد الأيام)
    shift = num_days // 2
    
    for i in range(num_days):
        # قيم الفترة الأولى
        first_start = int(i * part_size) + 1
        first_end = int((i + 1) * part_size)
        if i == num_days - 1:
            first_end = int(amount)
        
        # قيم الفترة الثانية (مع إزاحة دائرية)
        second_index = (i + shift) % num_days
        second_start = int(second_index * part_size) + 1
        second_end = int((second_index + 1) * part_size)
        if second_index == num_days - 1:
            second_end = int(amount)
        
        first_period_values.append(f"{first_start}-{first_end}")
        second_period_values.append(f"{second_start}-{second_end}")
    
    # إنشاء DataFrame
    data = {
        ' ': [''] * num_days,  # عمود فارغ للتباعد
        'اليوم': days,
        'صباحاً': first_period_values,
        'مساءً': second_period_values,
        '  ': [''] * num_days   # عمود فارغ للتباعد
    }
    
    df = pd.DataFrame(data)
    return df, amount, num_days

def create_beautiful_table_image(df, amount, num_days):
    """إنشاء صورة جميلة للجدول بخط كبير وواضح"""
    
    # البحث عن خط يدعم العربية
    font_path = None
    windows_font_paths = [
        'C:/Windows/Fonts/Arial.ttf',
        'C:/Windows/Fonts/trado.ttf',
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
    
    # إعداد الخطوط - خط كبير وواضح
    header_font = fm.FontProperties(fname=font_path, size=18, weight='bold')  # رؤوس الأعمدة
    cell_font = fm.FontProperties(fname=font_path, size=16)  # محتوى الجدول
    title_font = fm.FontProperties(fname=font_path, size=22, weight='bold')  # العنوان
    
    # تحديد حجم الصورة
    fig_height = max(8, num_days * 0.6 + 3)
    fig, ax = plt.subplots(figsize=(16, fig_height))
    ax.axis('off')
    ax.axis('tight')
    
    # تجهيز البيانات
    table_data = []
    
    # إضافة صف المقدار في الأعلى
    table_data.append(['', reshape_arabic_text(f'المقدار: {amount}'), '', ''])
    
    # إضافة رؤوس الأعمدة
    headers = [
        reshape_arabic_text(''),
        reshape_arabic_text('اليوم'),
        reshape_arabic_text('صباحاً'),
        reshape_arabic_text('مساءً'),
        reshape_arabic_text('')
    ]
    table_data.append(headers)
    
    # إضافة البيانات
    for index, row in df.iterrows():
        row_data = [
            '',
            reshape_arabic_text(row['اليوم']),
            reshape_arabic_text(row['صباحاً']),
            reshape_arabic_text(row['مساءً']),
            ''
        ]
        table_data.append(row_data)
    
    # إنشاء الجدول
    table = ax.table(
        cellText=table_data,
        loc='center',
        cellLoc='center',
        colWidths=[0.05, 0.25, 0.25, 0.25, 0.05]  # أعمدة جانبية صغيرة للتباعد
    )
    
    # تنسيق الجدول
    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.scale(1.5, 2.2)  # تكبير الخلايا
    
    # تنسيق الخلايا
    for (i, j), cell in table.get_celld().items():
        # تطبيق الخط
        if i == 1:  # صف الرؤوس
            cell.set_text_props(fontproperties=header_font, ha='center')
        else:
            cell.set_text_props(fontproperties=cell_font, ha='center')
        
        # ألوان الخلايا
        if i == 0:  # صف المقدار
            if j == 1:  # عمود المقدار فقط
                cell.set_facecolor('#FFD700')  # ذهبي
                cell.set_text_props(weight='bold', fontproperties=header_font)
            else:
                cell.set_facecolor('#f0f0f0')
        
        elif i == 1:  # صف الرؤوس
            cell.set_facecolor('#4CAF50')  # أخضر
            cell.set_text_props(weight='bold', color='white', fontproperties=header_font)
        
        else:  # باقي الصفوف
            if j == 1:  # عمود اليوم
                cell.set_facecolor('#E3F2FD')  # أزرق فاتح
                cell.set_text_props(weight='bold', fontproperties=cell_font)
            elif j in [2, 3]:  # عمودي القيم
                # تلوين متناوب للصفوف
                if i % 2 == 0:
                    cell.set_facecolor('#F5F5F5')  # رمادي فاتح جداً
                else:
                    cell.set_facecolor('#FFFFFF')  # أبيض
            else:  # الأعمدة الجانبية الفارغة
                cell.set_facecolor('#FFFFFF')
                cell.set_text_props(color='white')  # إخفاء النص الفارغ
        
        # حدود الخلايا
        cell.set_edgecolor('#333333')
        cell.set_linewidth(1.5)
        
        # إضافة padding داخلي
        cell.PAD = 0.1
    
    # إضافة عنوان رئيسي
    title_text = reshape_arabic_text(f'📊 جدول تقسيم {amount} على {num_days} أيام')
    plt.suptitle(title_text, fontproperties=title_font, y=0.98, fontsize=22)
    
    # تحسين التباعد
    plt.subplots_adjust(top=0.92, bottom=0.05)
    
    # حفظ الصورة بجودة عالية
    img_bytes = io.BytesIO()
    plt.savefig(
        img_bytes,
        format='PNG',
        dpi=400,  # دقة عالية جداً
        bbox_inches='tight',
        facecolor='white',
        edgecolor='none',
        pad_inches=0.3
    )
    plt.close()
    img_bytes.seek(0)
    
    return img_bytes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بداية المحادثة"""
    user = update.effective_user
    welcome_text = (
        f"👋 أهلاً {user.first_name}!\n\n"
        "🤖 *بوت تقسيم المقدار*\n"
        "سأقوم بتقسيم أي رقم تدخله على عدد محدد من الأيام\n"
        "وسأرسل لك **صورة** بخط كبير وواضح 📸\n\n"
        "🔹 *الرجاء إدخال المقدار:*"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء العملية"""
    await update.message.reply_text(
        "❌ تم إلغاء العملية.\n"
        "لبدء عملية جديدة أرسل /start"
    )
    return ConversationHandler.END

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المقدار"""
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
            "🔹 *الرجاء إدخال عدد الأيام:*"
        )
        
        return DAYS
        
    except ValueError:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح")
        return AMOUNT

async def get_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال عدد الأيام وإنشاء الصورة"""
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
        
        # إنشاء الصورة الجميلة
        img_bytes = create_beautiful_table_image(df, amount, num_days)
        
        # حذف رسالة الانتظار
        await wait_msg.delete()
        
        # إرسال الصورة فقط (بدون نص)
        await update.message.reply_photo(
            photo=img_bytes,
            caption=None  # بدون تعليق
        )
        
        # رسالة نجاح بسيطة
        await update.message.reply_text(
            "✅ تمت العملية بنجاح!\n"
            "لبدء عملية جديدة أرسل /start"
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

def main():
    """الدالة الرئيسية"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ خطأ: لم يتم العثور على TELEGRAM_BOT_TOKEN")
        return
    
    # إنشاء التطبيق
    app = Application.builder().token(token).build()
    
    # إضافة معالج المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    app.add_handler(conv_handler)
    
    print("✅ البوت يعمل الآن... جاهز لاستقبال الأوامر")
    
    # تشغيل البوت
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0
    )

# للاستخدام مع Railway
application = main

if __name__ == '__main__':
    main()