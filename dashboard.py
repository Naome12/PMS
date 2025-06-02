from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app)

def get_db_connection():
    """Create a database connection"""
    return psycopg2.connect(
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT')
    )

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """Get current parking statistics"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get current vehicles in parking
            cur.execute("""
                SELECT COUNT(*) as current_vehicles 
                FROM plates 
                WHERE exit_time IS NULL
            """)
            current_vehicles = cur.fetchone()['current_vehicles']

            # Get total number of entries
            cur.execute("""
                SELECT COUNT(*) as total_entries 
                FROM plates
            """)
            total_entries = cur.fetchone()['total_entries']

            # Get today's revenue
            cur.execute("""
                SELECT COUNT(*) as total_payments, 
                       SUM(CASE WHEN payment_status = 1 THEN paid_amount ELSE 0 END) as today_revenue
                FROM plates 
                WHERE entry_time >= CURRENT_DATE
            """)
            today_stats = cur.fetchone()

            # Get recent activities
            cur.execute("""
                SELECT plate_number, entry_time, exit_time, payment_status, paid_amount
                FROM plates 
                ORDER BY entry_time DESC 
                LIMIT 10
            """)
            recent_activities = cur.fetchall()

            # Get unauthorized exits for count
            cur.execute("""
                SELECT COUNT(*) as unauthorized_count FROM plates 
                WHERE exit_time IS NOT NULL 
                AND payment_status = 0
            """)
            unauthorized_exits_count = cur.fetchone()['unauthorized_count']

            return jsonify({
                'current_vehicles': current_vehicles,
                'total_entries': total_entries,
                'today_revenue': today_stats['today_revenue'] or 0, # Handle potential null sum
                'recent_activities': recent_activities,
                'unauthorized_exits_count': unauthorized_exits_count
            })
    finally:
        conn.close()

@app.route('/api/vehicles')
def get_vehicles():
    """Get current vehicles in parking"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT plate_number, entry_time, payment_status, paid_amount
                FROM plates 
                WHERE exit_time IS NULL
                ORDER BY entry_time DESC
            """)
            vehicles = cur.fetchall()
            return jsonify(vehicles)
    finally:
        conn.close()

@app.route('/api/alerts')
def get_alerts():
    """Get recent unauthorized exit attempts"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Fetch alerts directly from the endpoint that gets their count
            # This avoids redundant queries and ensures consistency
            cur.execute("""
                SELECT plate_number, entry_time, exit_time
                FROM plates 
                WHERE exit_time IS NOT NULL 
                AND payment_status = 0
                ORDER BY exit_time DESC 
                LIMIT 10
            """)
            alerts = cur.fetchall()

            return jsonify(alerts)
    finally:
        conn.close()

def emit_parking_event(event_type, data):
    """Emit a parking event to connected clients"""
    socketio.emit('parking_event', {
        'type': event_type,
        'data': data,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) 