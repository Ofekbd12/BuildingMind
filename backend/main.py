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
    r = requests.post(url, json=payload, headers=headers)
    print(f"WhatsApp Response: {r.status_code}")

# --- UI (ELEGANT DESIGN) ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #e74c3c;">Password incorrect</p>' if error else ""
    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; display: flex; justify-content: center; align-items: center; margin: 0; }}
        .box {{ background: white; padding: 40px; border-radius: 15px; text-align: center; width: 350px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }}
        input {{ width: 100%; padding: 12px; margin: 20px 0; border: 2px solid #eee; border-radius: 8px; text-align: center; }}
        button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }}
    </style></head><body><div class="box"><h2>MindBuilding</h2><form action="/auth" method="post"><input type="password" name="password" placeholder="סיסמה" required>{error_msg}<button type="submit">התחבר</button></form></div></body></html>
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
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    table_rows = "".join([f"<tr><td>{r['id']}</td><td>{r['location']}</td><td>{r.get('floor','-')}/{r.get('apartment','-')}</td><td>{r['description']}</td><td>{r['timestamp'].strftime('%d/%m %H:%M') if r['timestamp'] else '-'}</td></tr>" for r in rows])
    return f"<html><head><meta charset='UTF-8'><style>body{{font-family:sans-serif;direction:rtl;padding:20px;}} table{{width:100%;border-collapse:collapse;}} th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:right;}} th{{background:#4a148c;color:white;}}</style></head><body><h2>ניהול תקלות - התזמורת 38</h2><table><tr><th>ID</th><th>מיקום</th><th>קומה/דירה</th><th>תיאור</th><th>זמן</th></tr>{table_rows}</table></body></html>"

# --- WEBHOOK ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" in val:
            msg = val["messages"][0]
            phone = msg["from"]
            text = msg.get("text", {}).get("body", "").strip()

            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # 1. Deduplication
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg["id"],))
                conn.commit()
            except:
                conn.rollback()
                return Response(status_code=200)

            # 2. Get State
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            # 3. Bot Flow
            if not state or text.lower() in ["היי", "hi", "ביטול", "start"]:
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL, floor=NULL, apartment=NULL", (phone,))
                conn.commit()
                send_msg(phone, "שלום! איפה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. פח אשפה\n5. חניון\n6. גינה\n7. לובי קומתי\n8. פנים דירה")
            
            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if text in locs:
                    name = locs[text]
                    if text == "7":
                        cur.execute("UPDATE user_session_state SET step='FLOOR', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "באיזו קומה?")
                    elif text == "8":
                        cur.execute("UPDATE user_session_state SET step='APT', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, "באיזו דירה?")
                    else:
                        cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (name, phone))
                        send_msg(phone, f"נבחר {name}. תאר בקצרה את התקלה:")
                    conn.commit()
                else:
                    send_msg(phone, "נא לבחור מספר בין 1 ל-8.")

            elif state['step'] == 'FLOOR':
                cur.execute("UPDATE user_session_state SET step='DESC', floor=%s WHERE phone=%s", (text, phone))
                conn.commit()
                send_msg(phone, "תאר בקצרה את התקלה:")

            elif state['step'] == 'APT':
                cur.execute("UPDATE user_session_state SET step='DESC', apartment=%s WHERE phone=%s", (text, phone))
                conn.commit()
                send_msg(phone, "תאר בקצרה את התקלה:")

            elif state['step'] == 'DESC':
                cur.execute("INSERT INTO reports (phone, location, floor, apartment, description, status) VALUES (%s, %s, %s, %s, %s, 'טרם טופל')", (phone, state['location'], state.get('floor','N/A'), state.get('apartment','N/A'), text))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit()
                send_msg(phone, "תודה! הדיווח התקבל ויועבר לטיפול. ✨")

            cur.close(); conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
    return Response(status_code=200)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "12345":
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
