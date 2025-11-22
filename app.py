import logging
import secrets
import datetime
from flask import Flask, session, jsonify, request
from flask_cors import CORS
from featuretoggles import TogglesList

# --- Toggle 初始化 ---
class CinemaToggles(TogglesList):
    guest_checkout: bool

try:
    toggles = CinemaToggles('toggles.yaml')
except:
    class Mock: guest_checkout = False
    toggles = Mock()

app = Flask(__name__)
app.secret_key = 'cinema-secure-key'

# # --- 加入這段設定 ---
# app.config.update(
#     SESSION_COOKIE_HTTPONLY=True,
#     # 如果你是用 http://127.0.0.1 測試，設為 'Lax'
#     SESSION_COOKIE_SAMESITE='None', 
#     SESSION_COOKIE_SECURE=True,
#     # 注意：如果你未來上線用 HTTPS，這裡要改成 'None' 並且 SESSION_COOKIE_SECURE=True
# )
# # ------------------

CORS(app, supports_credentials=True) # 允許跨域 Cookie

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
        # === 實驗組 (Toggle ON) ===
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
        # === 對照組 (Toggle OFF) ===
        # 檢查是否已經登入
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

    # 2. 建立訂單 (模擬寫入資料庫)
    order_id = f"ORD-{secrets.token_hex(4).upper()}"
    order = {
        "id": order_id,
        "customer": customer_id,
        "movie": data.get('movie'),
        "seats": data.get('seats'),
        "time": datetime.datetime.now().isoformat()
    }
    bookings_db.append(order)
    
    return jsonify({
        "success": True, 
        "order_id": order_id,
        "target": "success.html"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)