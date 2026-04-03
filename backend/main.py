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
IMAGE_UPLOAD_DIR = "/app/uploaded_images"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")

def get_db_connection():
    return psycopg2.connect(DB_URL)

# --- ADMIN / WEBSITE ROUTES WITH BEAUTIFUL UI ---

@app.get("/", response_class=RedirectResponse)
async def root():
    return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #e74c3c; font-size: 14px;">Wrong password, please try again</p>' if error else ""
    # THE PREVIOUS ELEGANT LOGIN DESIGN
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
            .login-container {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 400px; text-align: center; }}
            .logo {{ font-size: 28px; font-weight: bold; color: #4a148c; margin-bottom: 5px; }}
            .address {{ font-size: 16px; color: #7f8c8d; margin-bottom: 30px; }}
            input[type="password"] {{ width: 100%; padding: 12px; margin-bottom: 20px; border: 2px solid #eee; border-radius: 8px; box-sizing: border-box; text-align: center; }}
            button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 16px; transition: background 0.3s; }}
            button:hover {{ background: #5a378a; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">MindBuilding</div>
            <div class="address">HaTizmoret 38</div>
            <h2>Admin Login 🏢</h2>
            <form action="/auth" method="post">
                <input type="password" name="password" placeholder="Enter Password" required>
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
        # Status Tag CSS
        s_val = r['status']
        s_class = "status-pending" if s_val == "טרם טופל" else "status-process" if s_val == "בטיפול" else "status-done"
        
        # Details HTML (Floor/Apt)
        details = ""
        if r.get('floor') and r['floor'] != 'N/A': details += f"Fl {r['floor']} "
        if r.get('apartment') and r['apartment'] != 'N/A': details += f"Apt {r['apartment']}"
        if not details: details = "-"

        table_rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>{details}</td>
            <td class="desc-cell">{r['description']}</td>
            <td><span class="status-tag {s_class}">{s_val}</span></td>
            <td>{r['timestamp'].strftime('%d/%m %H:%M')}</td>
        </tr>
        """
    # THE PREVIOUS ELEGANT REPORTS DESIGN
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; padding: 20px; background-color: #f4f7f6; }}
            .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); max-width: 1100px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 15px; }}
            .logo {{ font-size: 24px; font-weight: bold; color: #4a148c; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ text-align: right; padding: 15px; border-bottom: 1px solid #edf2f7; }}
            th {{ background-color: #f8f9fa; color: #7f8c8d; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; }}
            .desc-cell {{ color: #4a5568; font-size: 14px; max-width: 300px; }}
            .status-tag {{ font-weight: bold; padding: 5px 10px; border-radius: 15px; font-size: 12px; }}
            .status-pending {{ background: #fed7d7; color: #c53030; }}
            .status-process {{ background: #feebc8; color: #975a16; }}
            .status-done {{ background: #c6f6d5; color: #276749; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <div class="logo">MindBuilding - HaTizmoret 38 🏢</div>
                <a href="/logout" style="color:#e74c3c; text-decoration:none; font-weight:bold;">Logout</a>
            </div>
            <table>
                <thead>
                    <tr><th>ID</th><th>Location</th><th>Floor/Apt</th><th>Description</th><th>Status</th><th>Time</th></tr>
                </thead>
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

# --- WHATSAPP BOT LOGIC (Remains Stable & Persistent) ---

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

            # 1. Deduplication (Critical for Free Tier)
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

            # 2. Get Persistent State from DB
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (user_phone,))
            state = cur.fetchone()
            cur.close()
            conn.close()

            # 3. Flow Logic (The 8 Options)
            if not state or user_text.lower()
