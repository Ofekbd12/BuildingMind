import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import uvicorn

load_dotenv()
app = FastAPI()

# --- CONFIG ---
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
DB_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")

def get_db_connection():
    return psycopg2.connect(DB_URL)

def send_msg(to, text):
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, json=payload, headers=headers)

# --- ADMIN UI (THE PREMIUM PURPLE DESIGN) ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #ff4d4d; font-weight: bold;">סיסמה שגויה, נסה שוב</p>' if error else ""
    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
        .login-card {{ background: white; padding: 50px; border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.3); width: 100%; max-width: 400px; text-align: center; }}
        .logo {{ font-size: 32px; font-weight: 800; color: #4a148c; margin-bottom: 10px; letter-spacing: -1px; }}
        .subtitle {{ color: #7f8c8d; margin-bottom: 30px; font-size: 18px; }}
        input[type="password"] {{ width: 100%; padding: 15px; margin-bottom: 20px; border: 2px solid #f0f0f0; border-radius: 12px; outline: none; transition: 0.3s; font-size: 16px; text-align: center; }}
        input:focus {{ border-color: #764ba2; }}
        button {{ width: 100%; padding: 15px; background: #764ba2; color: white; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; font-size: 18px; transition: 0.3s; }}
        button:hover {{ background: #5a328a; transform: translateY(-2px); }}
    </style></head>
    <body><div class="login-card"><div class="logo">MindBuilding</div><div class="subtitle">התזמורת 38, ראשון לציון</div>
    <form action="/auth" method="post"><input type="password" name="password" placeholder="הקש סיסמת ניהול" required>{error_msg}<button type="submit">כניסה למערכת</button></form></div></body></html>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        res = RedirectResponse(url="/reports", status_code=302)
        res.set_cookie(key="admin_session", value="authenticated")
        return res
    return RedirectResponse(url="/login?error=True")

@app.get("/reports", response_class=HTMLResponse)
async def show_reports(request: Request, status_filter: str = None):
    if request.cookies.get("admin_session") != "authenticated": return RedirectResponse(url="/login")
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM reports"
    if status_filter:
        query += " WHERE status = %s"
        cur.execute(query + " ORDER BY timestamp DESC", (status_filter,))
    else:
        cur.execute(query + " ORDER BY timestamp DESC")
    
    rows = cur.fetchall()
    cur.close(); conn.close()
    
    table_rows = ""
    for r in rows:
        st = r['status']
        st_class = "st-pending" if st == "טרם טופל" else "st-progress" if st == "בטיפול" else "st-done"
        table_rows += f"""
        <tr>
            <td>#{r['id']}</td>
            <td><strong>{r['location']}</strong></td>
            <td>קומה {r.get('floor','-')} | דירה {r.get('apartment','-')}</td>
            <td>{r['description']}</td>
            <td><span class="status-pill {st_class}">{st}</span></td>
            <td>{r['timestamp'].strftime('%d/%m | %H:%M') if r['timestamp'] else '-'}</td>
        </tr>"""

    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: #f8f9fa; margin: 0; padding: 30px; }}
        .dashboard {{ background: white; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); max-width: 1200px; margin: auto; overflow: hidden; }}
        .header {{ background: #4a148c; color: white; padding: 25px 40px; display: flex; justify-content: space-between; align-items: center; }}
        .filters {{ padding: 20px 40px; background: #fdfdfd; border-bottom: 1px solid #eee; display: flex; gap: 10px; }}
        .filter-btn {{ padding: 8px 15px; border-radius: 20px; text-decoration: none; font-size: 14px; background: #eee; color: #666; transition: 0.2s; }}
        .filter-btn:hover, .filter-btn.active {{ background: #764ba2; color: white; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: right; padding: 20px; background: #fafafa; color: #888; font-size: 13px; text-transform: uppercase; border-bottom: 2px solid #eee; }}
        td {{ padding: 20px; border-bottom: 1px solid #f0f0f0; color: #333; }}
        .status-pill {{ padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
        .st-pending {{ background: #ffe5e5; color: #d63031; }}
        .st-progress {{ background: #fff4e5; color: #e67e22; }}
        .st-done {{ background: #e5f9e7; color: #27ae60; }}
        .logout {{ color: #ffbcbc; text-decoration: none; font-weight: bold; font-size: 14px; }}
    </style></head><body>
    <div class="dashboard">
        <div class="header">
            <h1 style="margin:0; font-size:24px;">ניהול תקלות - MindBuilding</h1>
            <a href="/logout" class="logout">התנתקות מהמערכת</a>
        </div>
        <div class="filters">
            <span style="margin-left:10px; align-self:center; font-weight:bold; color:#777;">סינון:</span>
            <a href="/reports" class="filter-btn">הכל</a>
            <a href="/reports?status_filter=טרם טופל" class="filter-btn">טרם טופל</a>
            <a href="/reports?status_filter=בטיפול" class="filter-btn">בטיפול</a>
            <a href="/reports?status_filter=בוצע" class="filter-btn">בוצע</a>
        </div>
        <table><thead><tr><th>ID</th><th>מיקום</th><th>פרטי מגורים</th><th>תיאור התקלה</th><th>סטטוס</th><th>זמן דיווח</th></tr></thead>
        <tbody>{table_rows}</tbody></table></div></body></html>
    """

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login")
    res.delete_cookie("admin_session")
    return res

# --- WEBHOOK LOGIC (FULL FLOW) ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            
            # Handling image or text
            user_text = ""
            if "text" in msg:
                user_text = msg["text"]["body"].strip()
            elif "image" in msg:
                user_text = "[תמונה נשלחה]" # Here we could add logic to save image ID

            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Deduplication
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg["id"],))
                conn.commit()
            except:
                conn.rollback(); return Response(status_code=200)

            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            if not state or user_text.lower() in ["היי", "hi", "ביטול", "start"]:
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL, floor=NULL, apartment=NULL", (phone,))
                conn.commit()
                send_msg(phone, "שלום! איפה קרתה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. פח אשפה\n5. חניון\n6. גינה\n7. לובי קומתי\n8. פנים דירה")
            
            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if user_text in locs:
                    name = locs[user_text]
                    if user_text == "7":
                        cur.execute("UPDATE user_session_state SET step='FLOOR', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "באיזו קומה (1-12)?")
                    elif user_text == "8":
                        cur.execute("UPDATE user_session_state SET step='APT', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "מה מספר הדירה?")
                    else:
                        cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, f"נבחר {name}. תאר בקצרה את התקלה (ניתן לשלוח גם תמונה):")
                    conn.commit()
                else:
                    send_msg(phone, "נא לבחור מספר 1-8.")

            elif state['step'] == 'FLOOR':
                cur.execute("UPDATE user_session_state SET step='DESC', floor=%s WHERE phone=%s", (user_text, phone))
                conn.commit()
                send_msg(phone, "תאר בקצרה את התקלה (ניתן לשלוח גם תמונה):")

            elif state['step'] == 'APT':
                cur
