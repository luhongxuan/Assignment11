import logging
import secrets
from flask import Flask, session, jsonify, request
from flask_cors import CORS
from featuretoggles import TogglesList

# --- 設定日誌 ---
logging.basicConfig(level=logging.INFO)

# --- 1. 初始化 Toggle (讀取 yaml) ---
class TicketToggles(TogglesList):
    guest_checkout: bool

try:
    toggles = TicketToggles('toggles.yaml')
except Exception as e:
    logging.warning(f"Toggle 載入失敗，使用預設值: {e}")
    class MockToggle: guest_checkout = False
    toggles = MockToggle()

app = Flask(__name__)
app.secret_key = 'devsecops-class-secret-key' # 用於加密 Session

# --- 2. 安全性配置 (CORS) ---
# 允許跨域請求，這讓你的前端 HTML (file://) 可以呼叫這個 API
CORS(app, supports_credentials=True)

# --- 3. A&A 邏輯：產生訪客 Token ---
def generate_guest_token():
    token = secrets.token_urlsafe(16)
    session['guest_token'] = token
    session['role'] = 'guest'
    return token

# --- API 路由 ---

@app.route('/api/route-decision', methods=['GET'])
def route_decision():
    """
    前端詢問：「我按下購買按鈕後要去哪？」
    後端回答：根據 Toggle 狀態與登入狀態決定。
    """
    logging.info(f"收到請求，目前 Toggle 狀態: {toggles.guest_checkout}")

    # 情況 A: 實驗開啟 (Toggle ON)
    if toggles.guest_checkout:
        token = generate_guest_token() # 賦予臨時權限
        return jsonify({
            "action": "redirect",
            "target": "guest.html",
            "mode": "guest_experiment",
            "debug_token": token 
        })
    
    # 情況 B: 實驗關閉 (Toggle OFF) -> 走傳統流程
    else:
        # 檢查是否已登入
        if 'user_id' in session:
            return jsonify({
                "action": "redirect",
                "target": "standard.html",
                "mode": "standard_member"
            })
        else:
            return jsonify({
                "action": "redirect",
                "target": "login.html",
                "mode": "login_required"
            })

@app.route('/api/login', methods=['POST'])
def login():
    # 模擬登入 API
    data = request.json
    session['user_id'] = data.get('username', 'user')
    session['role'] = 'member'
    return jsonify({"status": "ok", "target": "standard.html"})

if __name__ == '__main__':
    print("Backend Server Running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)