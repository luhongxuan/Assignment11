import logging
import secrets
import datetime
import os
from flask import Flask, session, jsonify, request, render_template
from flask_cors import CORS
from featuretoggles import TogglesList
from werkzeug.middleware.proxy_fix import ProxyFix

SEAT_MAP = [
    {"id": "A1", "row": "A", "col": 1, "type": "front", "status": 0},
    {"id": "A2", "row": "A", "col": 2, "type": "front", "status": 0},
    {"id": "A3", "row": "A", "col": 3, "type": "center", "status": 0}, # 視野最好
    {"id": "A4", "row": "A", "col": 4, "type": "front", "status": 0},
    {"id": "A5", "row": "A", "col": 5, "type": "aisle", "status": 1}, # 假裝有人買了
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
    class Mock: 
        guest_checkout = False
        auto_seating = False
    toggles = Mock()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-for-local-only')

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config.update(
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE=True
)

CORS(app, supports_credentials=True)

@app.route('/')
def page_index():
    return render_template('index.html')

@app.route('/login.html')
def page_login():
    return render_template('login.html')

@app.route('/booking_std.html')
def page_booking_std():
    return render_template('booking_std.html')

@app.route('/booking_guest.html')
def page_booking_guest():
    return render_template('booking_guest.html')

@app.route('/success.html')
def page_success():
    return render_template('success.html')

# --- 資料庫模擬 (In-Memory) ---
bookings_db = []

# --- Helper Functions ---
def generate_guest_token():
    return secrets.token_urlsafe(24) # 產生高強度隨機 Token

# --- API Endpoints ---

@app.route('/api/init-flow', methods=['GET'])
def init_flow():
    """
    [核心路由] 當用戶點擊「開始訂票」時呼叫
    由後端決定用戶該去哪裡 (Pattern: Server-Side Routing Logic)
    """
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
    # 模擬登入驗證
    if data.get('username') == 'admin' and data.get('password') == '1234':
        session['user_id'] = 'admin'
        session['role'] = 'member'
        return jsonify({"success": True, "target": "booking_std.html"})
    return jsonify({"success": False, "message": "帳號密碼錯誤"}), 401

@app.route('/api/seat-config', methods=['GET'])
def get_seat_config():
    """
    前端載入頁面時呼叫此 API，詢問：「我該顯示地圖還是偏好選項？」
    """
    mode = "auto" if toggles.auto_seating else "manual"
    
    response = {
        "mode": mode,
        "seats": [],      # 手動模式才需要回傳地圖
        "preferences": [] # 自動模式才需要回傳選項
    }

    if mode == "manual":
        # 回傳目前所有座位狀態
        response["seats"] = SEAT_MAP
    else:
        # 回傳可用的偏好選項
        response["preferences"] = [
            {"key": "center", "label": "👑 視野最佳 (中間區域)"},
            {"key": "aisle",  "label": "🏃 進出方便 (靠走道)"},
            {"key": "back",   "label": "🕶️ 隱密性高 (後排)"},
            {"key": "front",  "label": "🔥 臨場感強 (前排)"}
        ]
        
    logging.info(f"Seat Config Requested. Mode: {mode}")
    return jsonify(response)

def allocate_seats(pref, count):
    """
    [演算法] 根據偏好自動找空位
    """
    count = int(count)
    available = [s for s in SEAT_MAP if s['status'] == 0]
    
    # 簡單的優先順序邏輯
    if pref == 'center':
        # 找 Col=3 的位子
        candidates = [s for s in available if s['col'] == 3]
    elif pref == 'aisle':
        # 找 Col=1 或 5
        candidates = [s for s in available if s['col'] in [1, 5]]
    elif pref == 'back':
        # 找 Row=B
        candidates = [s for s in available if s['row'] == 'B']
    else:
        # 預設從前面開始
        candidates = available
        
    # 如果位子不夠，就隨便塞
    if len(candidates) < count:
        candidates = available
        
    if len(candidates) < count:
        return None # 沒位子了
        
    # 選出前 N 個位子，並將狀態改為已售出 (模擬)
    selected = candidates[:count]
    ids = []
    for s in selected:
        s['status'] = 1 # 鎖定座位
        ids.append(s['id'])
        
    return ids

@app.route('/api/book', methods=['POST'])
def book_ticket():
    """
    [核心交易] 處理訂票，同時支援 會員 與 訪客
    """
    data = request.json
    role = session.get('role')
    
    # 1. 安全性檢查：根據身份驗證請求
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
        # 模式 A: 自動配位 (前端傳來的是 preference)
        pref = data.get('preference')
        count = data.get('count', 1)
        assigned_seats = allocate_seats(pref, count)
        if not assigned_seats:
            return jsonify({"success": False, "error": "所選區域已無空位"}), 400
        logging.info(f"Auto-Allocated Seats: {assigned_seats}")
    else:
        # 模式 B: 手動選位 (前端傳來的是 seat_ids)
        assigned_seats = data.get('selected_seats') # 例如 ['A1', 'A2']
        # 這裡應該要檢查位子是否還空著，MVP 先跳過
        logging.info(f"User Selected Seats: {assigned_seats}")

    # 2. 建立訂單 (模擬寫入資料庫)
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
        "order_id": order_id, # 模擬 ID
        "seats": assigned_seats, # 回傳告訴使用者他買到哪
        "target": "success.html"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)