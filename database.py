import os
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("❌ DATABASE_URL غير موجود في المتغيرات البيئية")
        return None
    
    try:
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None

def init_database():
    """إنشاء الجداول إذا لم تكن موجودة"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # جدول المستخدمين
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMP,
                last_active TIMESTAMP,
                total_operations INTEGER DEFAULT 0
            )
        ''')
        
        # جدول العمليات
        cur.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount FLOAT,
                num_days INTEGER,
                result_data TEXT,
                created_at TIMESTAMP
            )
        ''')
        
        # جدول المفضلة
        cur.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                name TEXT,
                amount FLOAT,
                num_days INTEGER,
                created_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ تم إنشاء جداول قاعدة البيانات بنجاح")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء الجداول: {e}")
        return False

# دوال المستخدمين
def get_or_create_user(user_id, username, first_name, last_name=None):
    """الحصول على المستخدم أو إنشائه"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        
        # التحقق من وجود المستخدم
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        now = datetime.datetime.now()
        
        if not user:
            # مستخدم جديد
            cur.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, first_seen, last_active)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user_id, username, first_name, last_name, now, now))
            conn.commit()
            logger.info(f"✅ مستخدم جديد: {first_name}")
        else:
            # تحديث آخر ظهور
            cur.execute('''
                UPDATE users SET last_active = %s, username = %s, first_name = %s, last_name = %s
                WHERE user_id = %s
            ''', (now, username, first_name, last_name, user_id))
            conn.commit()
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في get_or_create_user: {e}")
        return False

def save_operation(user_id, amount, num_days, result_data=""):
    """حفظ عملية في السجل"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        now = datetime.datetime.now()
        
        cur.execute('''
            INSERT INTO operations (user_id, amount, num_days, result_data, created_at)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, amount, num_days, result_data, now))
        
        # زيادة عدد عمليات المستخدم
        cur.execute('''
            UPDATE users SET total_operations = total_operations + 1
            WHERE user_id = %s
        ''', (user_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في save_operation: {e}")
        return False

def get_user_operations(user_id, limit=10):
    """استرجاع آخر عمليات المستخدم"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT amount, num_days, created_at FROM operations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        ''', (user_id, limit))
        
        operations = cur.fetchall()
        cur.close()
        conn.close()
        return operations
    except Exception as e:
        logger.error(f"❌ خطأ في get_user_operations: {e}")
        return []

def add_favorite(user_id, name, amount, num_days):
    """إضافة عنصر للمفضلة"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        now = datetime.datetime.now()
        
        cur.execute('''
            INSERT INTO favorites (user_id, name, amount, num_days, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, name, amount, num_days, now))
        
        fav_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        return fav_id
    except Exception as e:
        logger.error(f"❌ خطأ في add_favorite: {e}")
        return None

def get_favorites(user_id):
    """استرجاع مفضلة المستخدم"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT id, name, amount, num_days FROM favorites
            WHERE user_id = %s
            ORDER BY created_at DESC
        ''', (user_id,))
        
        favorites = cur.fetchall()
        cur.close()
        conn.close()
        return favorites
    except Exception as e:
        logger.error(f"❌ خطأ في get_favorites: {e}")
        return []

def delete_favorite(fav_id, user_id):
    """حذف عنصر من المفضلة"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute('''
            DELETE FROM favorites WHERE id = %s AND user_id = %s
        ''', (fav_id, user_id))
        
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return deleted
    except Exception as e:
        logger.error(f"❌ خطأ في delete_favorite: {e}")
        return False

def get_bot_stats():
    """إحصائيات عامة عن البوت"""
    conn = get_db_connection()
    if not conn:
        return {
            'total_users': 0,
            'total_operations': 0,
            'operations_sum': 0,
            'active_today': 0
        }
    
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM operations")
        total_ops = cur.fetchone()['count']
        
        cur.execute("SELECT SUM(total_operations) FROM users")
        ops_sum = cur.fetchone()['sum'] or 0
        
        cur.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '1 day'")
        active_today = cur.fetchone()['count']
        
        cur.close()
        conn.close()
        
        return {
            'total_users': total_users,
            'total_operations': total_ops,
            'operations_sum': ops_sum,
            'active_today': active_today
        }
    except Exception as e:
        logger.error(f"❌ خطأ في get_bot_stats: {e}")
        return {
            'total_users': 0,
            'total_operations': 0,
            'operations_sum': 0,
            'active_today': 0
        }