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
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error sending: {e}")

# --- ADMIN UI (PREMIUM PURPLE & BUTTONS) ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
        .card {{ background: white; padding: 40px; border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.2); width: 320px; text-align: center; }}
        input {{ width: 100%; padding: 12px; margin: 20px 0; border: 2px solid #eee; border-radius: 10px; text-align: center; }}
        button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; }}
    </style></head><body><div class="card"><h2>MindBuilding</h2><p>התזמורת 38</p>
    <form action="/auth" method="post"><input type="password" name="password" placeholder="סיסמה" required>
    {"<p style='color:red;'>שגוי</p>" if error else ""}<button type="submit">התחבר</button></form></div></body></html>
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
    if status_filter:
        cur.execute("SELECT * FROM reports WHERE status = %s ORDER BY timestamp DESC", (status_filter,))
    else:
        cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    
    table_rows = ""
    for r in rows:
        st = r['status']
        st_class = "st-pending" if st == "טרם טופל" else "st-progress" if st == "בטיפול" else "st-done"
        table_rows += f"""
        <tr>
            <td>#{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>ק' {r.get('floor','-')} | ד' {r.get('apartment','-')}</td>
            <td>{r['description']}</td>
            <td><span class="status-pill {st_class}">{st}</span></td>
            <td>{r['timestamp'].strftime('%d/%m %H:%M') if r['timestamp'] else '-'}</td>
        </tr>"""

    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: sans-serif; direction: rtl; background: #f4f7f6; margin: 0; padding: 20px; }}
        .header {{ background: #4a148c; color: white; padding: 20px; border-radius: 15px 15px 0 0; display: flex; justify-content: space-between; }}
        .filters {{ background: white; padding: 15px; display: flex; gap: 10px; border-bottom: 1px solid #eee; }}
        .filter-btn {{ padding: 8px 15px; border-radius: 20px; text-decoration: none; background: #eee; color: #666; font-size: 13px; }}
        .filter-btn:hover {{ background: #764ba2; color: white; }}
        table {{ width: 100%; background: white; border-collapse: collapse; border-radius: 0 0 15px 15px; overflow: hidden; }}
        th, td {{ padding: 15px; text-align: right; border-bottom: 1px solid #f0f0f0; }}
        .status-pill {{ padding: 5px 12px; border-radius: 15px; font-size: 11px; font-weight: bold; }}
        .st-pending {{ background: #ffe5e5; color: #d63031; }}
        .st-progress {{ background: #fff4e5; color: #e67e22; }}
        .st-done {{ background: #e5f9e7; color: #27ae60; }}
    </style></head><body>
    <div class="header"><h2>ניהול תקלות - התזמורת 38</h2><a href="/logout" style="color:white; text-decoration:none;">התנתק</a></div>
    <div class="filters">
        <b>סינון:</b>
        <a href="/reports" class="filter-btn">הכל</a>
        <a href="/reports?status_filter=טרם טופל" class="filter-btn">טרם טופל</a>
        <a href="/reports?status_filter=בטיפול" class="filter-btn">בטיפול</a>
        <a href="/reports?status_filter=בוצע" class="filter-btn">בוצע</a>
    </div>
    <table><thead><tr><th>ID</th><th>מיקום</th><th>פרטים</th><th>תיאור</th><th>סטטוס</th><th>זמן</th></tr></thead>
    <tbody>{table_rows}</tbody></table></body></html>
    """

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login")
    res.delete_cookie("admin_session")
    return res

# --- WEBHOOK (FIXED SYNTAX) ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            user_text = msg.get("text", {}).get("body", "").strip() if "text" in msg else "[מדיה]"

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

            if not state or user_text.lower() in ["היי", "hi", "ביטול"]:
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL, floor=NULL, apartment=NULL", (phone,))
                conn.commit()
                send_msg(phone, "שלום! איפה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. פח אשפה\n5. חניון\n6. גינה\n7. לובי קומתי\n8. פנים דירה")
            
            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if user_text in locs:
                    name = locs[user_text]
                    if user_text == "7":
                        cur.execute("UPDATE user_session_state SET step='FLOOR', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "באיזו קומה?")
                    elif user_text == "8":
                        cur.execute("UPDATE user_session_state SET step='APT', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "מה מספר הדירה?")
                    else:
                        cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, f"נבחר {name}. תאר בקצרה את התקלה:")
                    conn.commit()
                else:
                    send_msg(phone, "בחר 1-8.")

            elif state['step'] in ['FLOOR', 'APT']:
                field = 'floor' if state['step'] == 'FLOOR' else 'apartment'
                cur.execute(f"UPDATE user_session_state SET step='DESC', {field}=%s WHERE phone=%s", (user_text, phone))
                conn.commit()
                send_msg(phone, "תאר בקצרה את התקלה (ניתן לשלוח תמונה):")

            elif state['step'] == 'DESC':
                cur.execute("INSERT INTO reports (phone, location, floor, apartment, description, status) VALUES (%s, %s, %s, %s, %s, 'טרם טופל')", 
                           (phone, state['location'], state.get('floor','-'), state.get('apartment','-'), user_text))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit()
                send_msg(phone, "תודה! הדיווח נשמר. ✨")

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
