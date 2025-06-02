import os
import psycopg2
from psycopg2 import Error
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_db_connection():
    """Create a database connection"""
    try:
        connection = psycopg2.connect(
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT')
        )
        return connection
    except Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

def init_db():
    """Initialize database tables and columns"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Create plates table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plates (
                    id SERIAL PRIMARY KEY,
                    plate_number VARCHAR(10) NOT NULL,
                    payment_status INTEGER DEFAULT 0,
                    entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exit_time TIMESTAMP,
                    UNIQUE(plate_number, entry_time)
                )
            ''')
            
            # Add paid_amount column if it doesn't exist
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='plates' AND column_name='paid_amount') THEN
                        ALTER TABLE plates ADD COLUMN paid_amount INTEGER DEFAULT 0;
                    END IF;
                END $$
            """)

            conn.commit()
            print("Database initialized/updated successfully")
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            if conn:
                conn.close()

def log_plate_entry(plate_number):
    """Log a new plate entry"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO plates (plate_number, payment_status) VALUES (%s, %s)",
                (plate_number, 0)
            )
            conn.commit()
            return True
        except Error as e:
            print(f"Error logging plate entry: {e}")
            return False
        finally:
            if conn:
                conn.close()

def update_payment_status(plate_number, paid_amount):
    """Update payment status and paid amount for a plate"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE plates SET payment_status = 1, paid_amount = %s WHERE plate_number = %s AND payment_status = 0 AND exit_time IS NULL",
                (paid_amount, plate_number)
            )
            conn.commit()
            return True
        except Error as e:
            print(f"Error updating payment status: {e}")
            return False
        finally:
            if conn:
                conn.close()

def check_payment_status(plate_number):
    """Check if payment is complete for a plate"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payment_status FROM plates WHERE plate_number = %s ORDER BY entry_time DESC LIMIT 1",
                (plate_number,)
            )
            result = cursor.fetchone()
            return result[0] == 1 if result else False
        except Error as e:
            print(f"Error checking payment status: {e}")
            return False
        finally:
            if conn:
                conn.close()

def log_exit(plate_number):
    """Log plate exit time"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE plates SET exit_time = CURRENT_TIMESTAMP WHERE plate_number = %s AND exit_time IS NULL",
                (plate_number,)
            )
            conn.commit()
            return True
        except Error as e:
            print(f"Error logging exit: {e}")
            return False
        finally:
            if conn:
                conn.close()

def is_vehicle_inside(plate_number):
    """Check if a vehicle is still inside (has no exit time)"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM plates 
                WHERE plate_number = %s 
                AND exit_time IS NULL
                """,
                (plate_number,)
            )
            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Error as e:
            print(f"Error checking if vehicle is inside: {e}")
            return False
        finally:
            if conn:
                conn.close()

def is_vehicle_registered(plate_number):
    """Check if a vehicle with the given plate number exists in the database."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM plates WHERE plate_number = %s", (plate_number,))
            result = cursor.fetchone()
            return result[0] > 0
        except Error as e:
            print(f"Error checking if vehicle is registered: {e}")
            return False
        finally:
            if conn:
                conn.close()

def has_already_exited(plate_number):
    """Check if a vehicle with the given plate number has an exit time recorded for its last entry."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT exit_time FROM plates 
                WHERE plate_number = %s 
                ORDER BY entry_time DESC 
                LIMIT 1
            """, (plate_number,))
            result = cursor.fetchone()
            # If there's no entry, or the latest entry has an exit_time, return True (already exited or never entered)
            return result is None or result[0] is not None
        except Error as e:
            print(f"Error checking if vehicle has already exited: {e}")
            return False
        finally:
            if conn:
                conn.close()
