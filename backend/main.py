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

# --- ADMIN / WEBSITE ROUTES ---

@app.get("/", response_class=RedirectResponse)
async def root():
    return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: red;">Password incorrect</p>' if error else ""
    return f"""
    <html><body style="font-family:sans-serif; text-align:center; padding-top:80px; direction:rtl; background:#f0f2f5;">
        <div style="background:white; display:inline-block; padding:30px; border-radius:10px; shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2>ניהול ועד בית - התזמורת 38</h2>
            <form action="/auth" method="post">
                <input type="password" name="password" placeholder="הכנס סיסמה" style="padding:10px; width:200px;"><br><br>
                {error_msg}
                <button type="submit" style="padding:10px 20px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;">התחבר</button>
            </form>
        </div>
    </body></html>
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
        table_rows += f"""
        <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px;">{r['id']}</td>
            <td style="padding:10px;"><b>{r['location']}</b></td>
            <td style="padding:10px;">קומה: {r.get('floor','-')} | דירה: {r.get('apartment','-')}</td>
            <td style="padding:10px;">{r['description']}</td>
            <td style="padding:10px;">{r['status']}</td>
            <td style="padding:10px;">{r['timestamp'].strftime('%d/%m %H:%M')}</td>
        </tr>
        """
    
    return f"""
    <html><body style="font-family:sans-serif; direction:rtl; padding:20px; background:#f4f7f6;">
        <div style="max-width:1000px; margin:auto; background:white; padding:20px; border-radius:8px;">
            <h2>לוח דיווחי תקלות 🏢</h2>
            <table style="width:100%; border-collapse:collapse; text-align:right;">
                <thead style="background:#4a5568; color:white;">
                    <tr><th style="padding:10px;">ID</th><th>מיקום</th><th>פרטים</th><th>תיאור</th><th>סטטוס</th><th>זמן</th></tr>
                </thead>
                <tbody>{table_rows}</tbody>
            </table>
            <br><a href="/logout" style="color:red;">התנתק מהמערכת</a>
        </div>
    </body></html>
    """

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

# --- WHATSAPP BOT LOGIC (8 OPTIONS + PERSISTENT STATE) ---

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

            # 2. Get Current State from DB
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (user_phone,))
            state = cur.fetchone()
            cur.close()
            conn.close()

            # 3. Flow Logic
            if not state or user_text.lower() in ['היי', 'hi', 'ביטול']:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'SELECT_LOCATION') ON CONFLICT (phone) DO UPDATE SET step='SELECT_LOCATION', location=NULL, floor=NULL, apartment=NULL", (user_phone,))
                conn.commit()
                cur.close()
                conn.close()
                
                msg = ("שלום! איפה קרתה התקלה?\n"
                       "1. לובי 🏢\n2. מעלית גדולה 🛗\n3. מעלית קטנה 🛗\n"
                       "4. פח אשפה 🗑️\n5. חניון 🚗\n6. גינה 🌳\n"
                       "7. לובי קומתי 🏠\n8. פנים דירה 🔑")
                send_whatsapp_message(user_phone, msg)

            elif state['step'] == 'SELECT_LOCATION':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if user_text in locs:
                    loc_name = locs[user_text]
                    conn = get_db_connection()
                    cur = conn.cursor()
                    if user_text == "7":
                        cur.execute("UPDATE user_session_state SET step='GET_FLOOR', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_whatsapp_message(user_phone, "באיזו קומה (1-12)?")
                    elif user_text == "8":
                        cur.execute("UPDATE user_session_state SET step='GET_APT', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_whatsapp_message(user_phone, "מה מספר הדירה?")
                    else:
                        cur.execute("UPDATE user_session_state SET step='GET_DESC', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_whatsapp_message(user_phone, f"נבחר: {loc_name}. תאר בקצרה את התקלה:")
                    conn.commit()
                    cur.close()
                    conn.close()
                else:
                    send_whatsapp_message(user_phone, "נא לבחור מספר בין 1 ל-8.")

            elif state['step'] == 'GET_FLOOR':
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE user_session_state SET step='GET_DESC', floor=%s WHERE phone=%s", (user_text, user_phone))
                conn.commit()
                cur.close()
                conn.close()
                send_whatsapp_message
