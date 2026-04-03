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

# --- CONFIGURATION ---
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = "v22.0"
DB_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")

def get_db_connection():
    return psycopg2.connect(DB_URL)

# --- HELPER: SEND WHATSAPP ---
def send_msg(to, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        print(f"WhatsApp Response: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Error sending message: {e}")

# --- ADMIN UI (THE DESIGN YOU LIKED) ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color:red;">Password incorrect</p>' if error else ""
    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; display: flex; justify-content: center; align-items: center; margin: 0; }}
        .box {{ background: white; padding: 40px; border-radius: 15px; text-align: center; width: 300px; }}
        input {{ width: 100%; padding: 10px; margin: 15px 0; border: 1px solid #ddd; border-radius: 5px; }}
        button {{ width: 100%; padding: 10px; background: #764ba2; color: white; border: none; border-radius: 5px; cursor: pointer; }}
    </style></head><body><div class="box"><h2>MindBuilding</h2><form action="/auth" method="post"><input type="password" name="password" placeholder="סיסמה" required>{error_msg}<button type="submit">כניסה</button></form></div></body></html>
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
    
    table_rows = ""
    for r in rows:
        table_rows += f"<tr><td>{r['id']}</td><td>{r['location']}</td><td>{r.get('floor','-')}/{r.get('apartment','-')}</td><td>{r['description']}</td><td>{r['status']}</td></tr>"
    
    return f"<html><head><meta charset='UTF-8'><style>body{{font-family:sans-serif;direction:rtl;padding:20px;}} table{{width:100%;border-collapse:collapse;}} th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:right;}} th{{background:#eee;}}</style></head><body><h2>דיווחים - התזמורת 38</h2><table><tr><th>ID</th><th>מיקום</th><th>קומה/דירה</th><th>תיאור</th><th>סטטוס</th></tr>{table_rows}</table></body></html>"

# --- WEBHOOK ---
@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    data = await request.json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            msg_id = message["id"]
            user_phone = message["from"]
            user_text = message.get("text", {}).get("body", "").strip()

            # 1. Deduplication (Prevent double messages)
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback(); return Response(status_code=200)
            finally:
                cur.close(); conn.close()

            # 2. State Check
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (user_phone,))
            state = cur.fetchone()
            cur.close(); conn.close()

            # 3. Logic
            if not state or user_text.lower() in ['היי', 'hi', 'start', 'ביטול']:
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'STEP_1') ON CONFLICT (phone) DO UPDATE SET step='STEP_1', location=NULL, floor=NULL, apartment=NULL", (user_phone,))
                conn.commit(); cur.close(); conn.close()
                send_msg(user_phone, "שלום! איפה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. פח אשפה\n5. חניון\n6. גינה\n7. לובי קומתי\n8. פנים דירה")

            elif state['step'] == 'STEP_1':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if user_text in locs:
                    loc_name = locs[user_text]
                    conn = get_db_connection(); cur = conn.cursor()
                    if user_text == "7":
                        cur.execute("UPDATE user_session_state SET step='STEP_FLOOR', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_msg(user_phone, "באיזו קומה?")
                    elif user_text == "8":
                        cur.execute("UPDATE user_session_state SET step='STEP_APT', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_msg(user_phone, "באיזו דירה?")
                    else:
                        cur.execute("UPDATE user_session_state SET step='STEP_DESC', location=%s WHERE phone=%s", (loc_name, user_phone))
                        send_msg(user_phone, f"נבחר {loc_name}. תאר בקצרה את התקלה:")
                    conn.commit(); cur.close(); conn.close()
                else:
                    send_msg(user_phone, "נא לבחור 1-8.")

            elif state['step'] == 'STEP_FLOOR':
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("UPDATE user_session_state SET step='STEP_DESC', floor=%s WHERE phone=%s", (user_text, user_phone))
                conn.commit(); cur.close(); conn.close()
                send_msg(user_phone, "תאר בקצרה את התקלה:")

            elif state['step'] == 'STEP_APT':
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("UPDATE user_session_state SET step='STEP_DESC', apartment=%s WHERE phone=%s", (user_text, user_phone))
                conn.commit(); cur.close(); conn.close()
                send_msg(user_phone, "תאר בקצרה את התקלה:")

            elif state['step'] == 'STEP_DESC':
                conn = get_db_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO reports (phone, location, floor, apartment, description, status) VALUES (%s, %s, %s, %s, %s, 'טרם טופל')", 
                           (user_phone, state['location'], state.get('floor','N/A'), state.get('apartment','N/A'), user_text))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (user_phone,))
                conn.commit(); cur.close(); conn.close()
                send_msg(user_phone, "תודה! הדיווח נשמר. ✨")

    except Exception as e: print(f"Error: {e}")
    return Response(status_code=200)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "12345":
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
