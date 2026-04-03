import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
from fastapi import FastAPI, Request, Response, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import uvicorn

load_dotenv()
app = FastAPI()

# --- CONFIGURATION ---
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = "v22.0"
DB_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")

def get_db_connection():
    return psycopg2.connect(DB_URL)

# --- ADMIN UI (ELEGANT DESIGN) ---

@app.get("/", response_class=RedirectResponse)
async def root():
    return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #e74c3c; font-size: 14px;">Password incorrect, try again</p>' if error else ""
    return f"""
    <html>
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
            .login-container {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 350px; text-align: center; }}
            .logo {{ font-size: 28px; font-weight: bold; color: #4a148c; margin-bottom: 5px; }}
            input[type="password"] {{ width: 100%; padding: 12px; margin: 20px 0; border: 2px solid #eee; border-radius: 8px; box-sizing: border-box; text-align: center; }}
            button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">MindBuilding</div>
            <div>HaTizmoret 38</div>
            <form action="/auth" method="post">
                <input type="password" name="password" placeholder="Password" required>
                {error_msg}
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/reports", status_code=302)
        response.set_cookie(key="admin_session", value="authenticated")
        return response
    return RedirectResponse(url="/login?error=True")

@app.get("/reports", response_class=HTMLResponse)
async def show_reports(request: Request):
    if request.cookies.get("admin_session") != "authenticated":
        return RedirectResponse(url="/login")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    table_rows = ""
    for r in rows:
        s_val = r['status']
        s_class = "status-pending" if s_val == "טרם טופל" else "status-process" if s_val == "בטיפול" else "status-done"
        table_rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>Floor: {r.get('floor','-')} | Apt: {r.get('apartment','-')}</td>
            <td>{r['description']}</td>
            <td><span class="status-tag {s_class}">{s_val}</span></td>
            <td>{r['timestamp'].strftime('%d/%m %H:%M')}</td>
        </tr>
        """
    
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; padding: 20px; background-color: #f4f7f6; }}
            .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); max-width: 1100px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 15px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ text-align: right; padding: 15px; border-bottom: 1px solid #edf2f7; }}
            th {{ background-color: #f8f9fa; color: #7f8c8d; font-size: 12px; }}
            .status-tag {{ font-weight: bold; padding: 5px 10px; border-radius: 15px; font-size: 12px; }}
            .status-pending {{ background: #fed7d7; color: #c53030; }}
            .status-process {{ background: #feebc8; color: #975a16; }}
            .status-done {{ background: #c6f6d5; color: #276749; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <div style="font-size:24px; font-weight:bold; color:#4a148c;">Reports - MindBuilding</div>
                <a href="/logout" style="color:#e74c3c; text-decoration:none; font-weight:bold;">Logout</a>
            </div>
            <table>
                <thead><tr><th>ID</th><th>Location</th><th>Details</th><th>Description</th><th>Status</th><th>Time</th></tr></thead>
                <tbody>{table_rows}</tbody>
            </table>
        </div>
    </body>
    </html>
    """

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

# --- BOT LOGIC ---

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, json=payload, headers=headers)

@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    data = await request.json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            msg_id = message["id"]
            user_phone = message["from"]
            user_text = message.get("text", {}).get("body", "").strip()

            # 1. Deduplication
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback()
                return Response(status_code=200)
            finally:
                cur.close()
                conn.close()

            # 2. State Logic
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (user_phone,))
            state = cur.fetchone()
            cur.close()
            conn.close()

            if not state or user_text.lower() in ['היי', 'hi', 'ביטול', 'start']:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO user_session_state (phone
