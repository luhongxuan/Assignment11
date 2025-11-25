import logging
import secrets
import datetime
from flask import Flask, session, jsonify, request
from flask_cors import CORS
from featuretoggles import TogglesList

SEAT_MAP = [
    {"id": "A1", "row": "A", "col": 1, "type": "front", "status": 0},
    {"id": "A2", "row": "A", "col": 2, "type": "front", "status": 0},
    {"id": "A3", "row": "A", "col": 3, "type": "center", "status": 0},
    {"id": "A4", "row": "A", "col": 4, "type": "front", "status": 0},
    {"id": "A5", "row": "A", "col": 5, "type": "aisle", "status": 1},
    {"id": "B1", "row": "B", "col": 1, "type": "back",  "status": 0},
    {"id": "B2", "row": "B", "col": 2, "type": "back",  "status": 0},
    {"id": "B3", "row": "B", "col": 3, "type": "center", "status": 0},
]

# --- Toggle 初始化 ---
class CinemaToggles(TogglesList):
    guest_checkout: bool
    auto_seating: bool

try:
    toggles = CinemaToggles('toggles.yaml')
except:
    class Mock: guest_checkout = False
    toggles = Mock()

app = Flask(__name__)
app.secret_key = 'cinema-secure-key'
CORS(app, supports_credentials=True)

bookings_db = []

def generate_guest_token():
    return secrets.token_urlsafe(24)

@app.route('/api/init-flow', methods=['GET'])
def init_flow():
    if toggles.guest_checkout:
        token = generate_guest_token()
        session['guest_token'] = token
        session['role'] = 'guest'
        logging.info(f"Guest Flow Started. Token: {token[:8]}...")
        
        return jsonify({
            "action": "redirect",
            "target": "booking_guest.html",
            "message": "進入快速訂票模式"
        })
    else:
        if 'user_id' in session:
            return jsonify({"action": "redirect", "target": "booking_std.html"})
        else:
            return jsonify({"action": "redirect", "target": "login.html"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == 'admin' and data.get('password') == '1234':
        session['user_id'] = 'admin'
        session['role'] = 'member'
        return jsonify({"success": True, "target": "booking_std.html"})
    return jsonify({"success": False, "message": "帳號密碼錯誤"}), 401

@app.route('/api/seat-config', methods=['GET'])
def get_seat_config():
    mode = "auto" if toggles.auto_seating else "manual"
    
    response = {
        "mode": mode,
        "seats": [],      
        "preferences": [] 
    }

    if mode == "manual":
        response["seats"] = SEAT_MAP
    else:
        response["preferences"] = [
            {"key": "center", "label": "👑 視野最佳 (中間區域)"},
            {"key": "aisle",  "label": "🏃 進出方便 (靠走道)"},
            {"key": "back",   "label": "🕶️ 隱密性高 (後排)"},
            {"key": "front",  "label": "🔥 臨場感強 (前排)"}
        ]
        
    logging.info(f"Seat Config Requested. Mode: {mode}")
    return jsonify(response)

def allocate_seats(pref, count):
    count = int(count)
    available = [s for s in SEAT_MAP if s['status'] == 0]
    
    if pref == 'center':
        candidates = [s for s in available if s['col'] == 3]
    elif pref == 'aisle':
        candidates = [s for s in available if s['col'] in [1, 5]]
    elif pref == 'back':
        candidates = [s for s in available if s['row'] == 'B']
    else:
        candidates = available
        
    if len(candidates) < count:
        candidates = available
        
    if len(candidates) < count:
        return None
        
    selected = candidates[:count]
    ids = []
    for s in selected:
        s['status'] = 1
        ids.append(s['id'])
        
    return ids

@app.route('/api/book', methods=['POST'])
def book_ticket():
    data = request.json
    role = session.get('role')
    
    if role == 'guest':
        if 'guest_token' not in session:
            return jsonify({"error": "Security Violation: Invalid Guest Session"}), 403
        customer_id = f"GUEST-{data.get('email')}"
        logging.info("Processing GUEST order")
        
    elif role == 'member':
        if 'user_id' not in session:
            return jsonify({"error": "Session Expired"}), 401
        customer_id = f"MEMBER-{session.get('user_id')}"
        logging.info("Processing MEMBER order")
        
    else:
        return jsonify({"error": "Unauthorized"}), 401

    assigned_seats = []
    
    if toggles.auto_seating:
        pref = data.get('preference')
        count = data.get('count', 1)
        assigned_seats = allocate_seats(pref, count)
        if not assigned_seats:
            return jsonify({"success": False, "error": "所選區域已無空位"}), 400
        logging.info(f"Auto-Allocated Seats: {assigned_seats}")
    else:
        assigned_seats = data.get('selected_seats') # 例如 ['A1', 'A2']
        logging.info(f"User Selected Seats: {assigned_seats}")

    order_id = f"ORD-{secrets.token_hex(4).upper()}"
    order = {
        "id": order_id,
        "customer": customer_id,
        "movie": data.get('movie'),
        "seats": assigned_seats,
        "time": datetime.datetime.now().isoformat()
    }
    bookings_db.append(order)
    
    return jsonify({
        "success": True, 
        "order_id": order_id,
        "seats": assigned_seats,
        "target": "success.html"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)