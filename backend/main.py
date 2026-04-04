import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
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
    try: requests.post(url, json=payload, headers=headers)
    except: pass

def get_media_url(media_id):
    """שואב את הקישור הישיר לתמונה מוואטסאפ"""
    try:
        url = f"https://graph.facebook.com/v22.0/{media_id}"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        res = requests.get(url, headers=headers).json()
        return res.get("url")
    except: return None

# --- ADMIN ACTIONS ---
@app.post("/update_status/{report_id}/{new_status}")
async def update_status(request: Request, report_id: int, new_status: str):
    if request.cookies.get("admin_session") != "authenticated": return Response(status_code=401)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE reports SET status = %s WHERE id = %s", (new_status, report_id))
    conn.commit(); cur.close(); conn.close()
    return RedirectResponse(url="/reports", status_code=303)

# --- ADMIN UI ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #ff4d4d; font-weight: bold; font-size:14px;">סיסמה שגויה, נסה שוב</p>' if error else ""
    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
        .login-card {{ background: white; padding: 45px; border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.3); width: 100%; max-width: 360px; text-align: center; }}
        .logo {{ font-size: 32px; font-weight: 800; color: #4a148c; margin-bottom: 5px; letter-spacing: -1px; }}
        input[type="password"] {{ width: 100%; padding: 14px; margin-bottom: 15px; border: 2px solid #f0f0f0; border-radius: 12px; outline: none; text-align: center; box-sizing: border-box; }}
        button {{ width: 100%; padding: 14px; background: #764ba2; color: white; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; font-size: 17px; }}
    </style></head>
    <body><div class="login-card">
        <div class="logo">MindBuilding</div>
        <form action="/auth" method="post"><input type="password" name="password" placeholder="סיסמת מנהל" required>{error_msg}<button type="submit">התחברות</button></form>
    </div></body></html>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        res = RedirectResponse(url="/reports", status_code=303)
        res.set_cookie(key="admin_session", value="authenticated")
        return res
    return RedirectResponse(url="/login?error=True", status_code=303)

@app.get("/reports", response_class=HTMLResponse)
async def show_reports(request: Request):
    if request.cookies.get("admin_session") != "authenticated": return RedirectResponse(url="/login")
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    rows = cur.fetchall(); cur.close(); conn.close()
    
    table_rows = ""
    for r in rows:
        st = r['status']
        st_color = "#ff4d4d" if st == "טרם טופל" else "#ffa502" if st == "בטיפול" else "#2ed573"
        
        # לוגיקה לעמודת תמונה
        img_url = r.get('image_url')
        img_cell = f'<a href="{img_url}" target="_blank" style="color:#764ba2; font-weight:bold; text-decoration:none;">🖼️ צפה</a>' if img_url else '<span style="color:#ccc;">אין</span>'

        table_rows += f"""
        <tr>
            <td>#{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>דירה {r.get('apartment','-')} (ק' {r.get('floor','-')})</td>
            <td>{r['description']}</td>
            <td>{img_cell}</td>
            <td><span style="background:{st_color}22; color:{st_color}; padding:6px 12px; border-radius:15px; font-size:12px; font-weight:bold;">{st}</span></td>
            <td>
                <div style="display:flex; gap:8px;">
                    <form action="/update_status/{r['id']}/בטיפול" method="post" style="margin:0;"><button style="background:#ffa502; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px;">בטיפול</button></form>
                    <form action="/update_status/{r['id']}/טופל" method="post" style="margin:0;"><button style="background:#2ed573; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px;">טופל</button></form>
                </div>
            </td>
            <td style="font-size:12px; color:#888;">{r['timestamp'].strftime('%H:%M | %d/%m') if r['timestamp'] else '-'}</td>
        </tr>"""

    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: #f4f7f6; margin: 0; padding: 30px; }}
        .header {{ background: #34495e; color: white; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; border-radius: 12px 12px 0 0; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 0 0 12px 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
        th {{ background: #fdfdfd; padding: 18px; text-align: right; border-bottom: 2px solid #eee; color: #7f8c8d; font-size: 13px; }}
        td {{ padding: 18px; border-bottom: 1px solid #f1f1f1; color: #2c3e50; }}
        .logout {{ background: #e74c3c; color: white; padding: 8px 18px; border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: bold; }}
    </style></head><body>
    <div class="header"><h2 style="margin:0;">🏢 ניהול תקלות</h2><a href="/logout" class="logout">התנתקות</a></div>
    <table>
        <thead><tr><th>ID</th><th>מיקום</th><th>דירה/קומה</th><th>תיאור</th><th>תמונה</th><th>סטטוס</th><th>עדכון</th><th>זמן דיווח</th></tr></thead>
        <tbody>{table_rows}</tbody>
    </table></body></html>
    """

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login", status_code=303)
    res.delete_cookie("admin_session")
    return res

# --- WEBHOOK ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            msg_id = msg["id"]
            
            msg_type = msg.get("type")
            text = ""
            img_url = None

            if msg_type == "text":
                text = msg.get("text", {}).get("body", "").strip()
            elif msg_type == "image":
                media_id = msg["image"]["id"]
                img_url = get_media_url(media_id)
                text = msg.get("image", {}).get("caption", "[תמונה]")

            conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
            
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback(); return Response(status_code=200)

            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            if not state or text.lower() in ["היי", "hi", "תפריט"]:
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL", (phone,))
                conn.commit(); send_msg(phone, "שלום! איפה התקלה?\n1. לובי\n2. מעלית\n3. חניון\n4. פנים דירה")
            
            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית", "3":"חניון", "4":"פנים דירה"}
                if text in locs:
                    name = locs[text]
                    cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (name, phone))
                    conn.commit(); send_msg(phone, f"נבחר {name}. תאר את התקלה (ניתן לשלוח תמונה):")
                else: send_msg(phone, "אנא בחר מספר מהרשימה")

            elif state['step'] == 'DESC':
                cur.execute("INSERT INTO reports (phone, location, description, image_url, status) VALUES (%s, %s, %s, %s, 'טרם טופל')", 
                           (phone, state['location'], text, img_url))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit(); send_msg(phone, "תודה! הדיווח נשמר. ✨")

            cur.close(); conn.close()
    except Exception as e: print(f"Error: {e}")
    return Response(status_code=200)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "12345":
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
