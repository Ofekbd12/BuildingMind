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

# --- ADMIN ACTIONS ---
@app.post("/update_status/{report_id}/{new_status}")
async def update_status(request: Request, report_id: int, new_status: str):
    if request.cookies.get("admin_session") != "authenticated": return Response(status_code=401)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE reports SET status = %s WHERE id = %s", (new_status, report_id))
    conn.commit(); cur.close(); conn.close()
    return RedirectResponse(url="/reports", status_code=302)

# --- ADMIN UI (THE DESIGN YOU REQUESTED) ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: sans-serif; direction: rtl; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
        .card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; width: 350px; }}
        input {{ width: 100%; padding: 12px; margin: 20px 0; border: 1px solid #ddd; border-radius: 8px; }}
        button {{ width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }}
    </style></head><body><div class="card"><h2>כניסת ניהול - ועד הבית</h2><form action="/auth" method="post"><input type="password" name="password" placeholder="סיסמה" required><button type="submit">התחבר</button></form></div></body></html>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        res = RedirectResponse(url="/reports", status_code=302)
        res.set_cookie(key="admin_session", value="authenticated")
        return res
    return RedirectResponse(url="/login?error=True")

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
        img_html = f'<img src="{r.get("image_url")}" style="width:50px; border-radius:5px;">' if r.get("image_url") else '<span style="color:#ccc;">אין תמונה</span>'
        
        table_rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>דירה {r.get('apartment','-')} (ק' {r.get('floor','-')})</td>
            <td>{r['description']}</td>
            <td>{img_html}</td>
            <td><span style="background:{st_color}22; color:{st_color}; padding:5px 10px; border-radius:15px; font-size:12px; font-weight:bold;">{st}</span></td>
            <td>
                <div style="display:flex; gap:5px;">
                    <form action="/update_status/{r['id']}/בטיפול" method="post"><button style="background:#ffa502; color:white; border:none; padding:5px 8px; border-radius:4px; cursor:pointer; font-size:11px;">בטיפול</button></form>
                    <form action="/update_status/{r['id']}/טופל" method="post"><button style="background:#2ed573; color:white; border:none; padding:5px 8px; border-radius:4px; cursor:pointer; font-size:11px;">טופל</button></form>
                    <form action="/update_status/{r['id']}/סגור" method="post"><button style="background:#747d8c; color:white; border:none; padding:5px 8px; border-radius:4px; cursor:pointer; font-size:11px;">סגור</button></form>
                </div>
            </td>
            <td style="font-size:12px; color:#666;">{r['timestamp'].strftime('%H:%M %d/%m') if r['timestamp'] else '-'}</td>
        </tr>"""

    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: sans-serif; direction: rtl; background: #f8f9fa; padding: 20px; }}
        .header {{ background: #34495e; color: white; padding: 15px 25px; display: flex; justify-content: space-between; align-items: center; border-radius: 8px 8px 0 0; }}
        table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        th {{ background: #f1f2f6; padding: 15px; text-align: right; border-bottom: 2px solid #ddd; font-size: 14px; }}
        td {{ padding: 15px; border-bottom: 1px solid #eee; }}
        .logout {{ background: #ff4757; color: white; padding: 8px 15px; border-radius: 5px; text-decoration: none; font-size: 14px; }}
    </style></head><body>
    <div class="header">
        <h2 style="margin:0;">🏢 MindBuilding - התזמורת 38</h2>
        <a href="/logout" class="logout">התנתק</a>
    </div>
    <table>
        <thead><tr><th>ID</th><th>מיקום</th><th>דירה/קומה</th><th>תיאור</th><th>תמונה</th><th>סטטוס</th><th>פעולות</th><th>זמן</th></tr></thead>
        <tbody>{table_rows}</tbody>
    </table></body></html>
    """

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login")
    res.delete_cookie("admin_session")
    return res

# --- WEBHOOK ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]; phone = msg["from"]; text = msg.get("text", {}).get("body", "").strip()
            conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Deduplication
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg["id"],))
                conn.commit()
            except:
                conn.rollback(); return Response(status_code=200)

            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            if not state or text.lower() in ["היי", "hi", "ביטול"]:
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL", (phone,))
                conn.commit()
                send_msg(phone, "שלום! איפה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. פח אשפה\n5. חניון\n6. גינה\n7. לובי קומתי\n8. פנים דירה")
            
            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if text in locs:
                    cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (locs[text], phone))
                    conn.commit()
                    send_msg(phone, f"נבחר {locs[text]}. תאר את התקלה (ניתן לשלוח תמונה):")
                else: send_msg(phone, "בחר 1-8")

            elif state['step'] == 'DESC':
                cur.execute("INSERT INTO reports (phone, location, description, status) VALUES (%s, %s, %s, 'טרם טופל')", (phone, state['location'], text))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit()
                send_msg(phone, "תודה! הדיווח נשמר.")
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
