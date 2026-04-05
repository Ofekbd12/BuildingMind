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
        print(f"Error sending message: {e}")

def get_media_url(media_id):
    try:
        url = f"https://graph.facebook.com/v22.0/{media_id}"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        res = requests.get(url, headers=headers).json()
        return res.get("url")
    except:
        return None

# --- NEW: IMAGE PROXY TO FIX 401 ERROR ---
@app.get("/view_image")
async def view_image(url: str):
    """Downloads the image from FB servers using the token and serves it to the browser."""
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        res = requests.get(url, headers=headers)
        return Response(content=res.content, media_type="image/jpeg")
    except Exception as e:
        return Response(content=f"Error loading image: {e}", status_code=500)

# --- HELPER: ROUTING LOGIC ---
def process_location_flow(phone, location, cur, conn):
    if location == "פנים דירה":
        cur.execute("UPDATE user_session_state SET step='WAIT_APT', location=%s WHERE phone=%s", (location, phone))
        conn.commit()
        send_msg(phone, "באיזו דירה מדובר? (1-46)")
    elif location == "לובי קומתי":
        cur.execute("UPDATE user_session_state SET step='WAIT_FLOOR', location=%s WHERE phone=%s", (location, phone))
        conn.commit()
        send_msg(phone, "באיזו קומה מדובר? (1-12)")
    else:
        cur.execute("UPDATE user_session_state SET step='DESC', location=%s WHERE phone=%s", (location, phone))
        conn.commit()
        send_msg(phone, f"נבחר {location}. תאר בבקשה את התקלה:")

# --- ADMIN ACTIONS ---
@app.post("/update_status/{report_id}/{new_status}")
async def update_status(request: Request, report_id: int, new_status: str):
    if request.cookies.get("admin_session") != "authenticated":
        return Response(status_code=401)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE reports SET status = %s WHERE id = %s RETURNING phone, location", (new_status, report_id))
    report = cur.fetchone()
    conn.commit()
    if report and new_status == "טופל":
        msg = f"עדכון משמח! התקלה שדיווחת עליה ב-{report['location']} טופלה. תודה על הסבלנות! ✨"
        send_msg(report['phone'], msg)
    cur.close(); conn.close()
    return RedirectResponse(url="/reports", status_code=303)

@app.post("/delete_report/{report_id}")
async def delete_report(request: Request, report_id: int):
    if request.cookies.get("admin_session") != "authenticated":
        return Response(status_code=401)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
    conn.commit(); cur.close(); conn.close()
    return RedirectResponse(url="/reports", status_code=303)

# --- ADMIN UI ---
@app.get("/", response_class=RedirectResponse)
async def root(): return "/login"

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #ff4d4d; font-weight: bold; font-size:14px; margin-bottom:15px;">סיסמה שגויה, נסה שוב</p>' if error else ""
    return f"""
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
        .login-card {{ background: white; padding: 45px; border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.3); width: 100%; max-width: 360px; text-align: center; }}
        .logo {{ font-size: 32px; font-weight: 800; color: #4a148c; margin-bottom: 5px; letter-spacing: -1px; }}
        .subtitle {{ color: #7f8c8d; font-size: 14px; margin-bottom: 30px; }}
        input[type="password"] {{ width: 100%; padding: 14px; margin-bottom: 15px; border: 2px solid #f0f0f0; border-radius: 12px; outline: none; text-align: center; box-sizing: border-box; }}
        button {{ width: 100%; padding: 14px; background: #764ba2; color: white; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; font-size: 17px; }}
    </style></head>
    <body><div class="login-card">
        <div class="logo">MindBuilding</div>
        <div class="subtitle">מערכת ניהול תקלות חכמה</div>
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
async def show_reports(request: Request, status_filter: str = "הכל"):
    if request.cookies.get("admin_session") != "authenticated":
        return RedirectResponse(url="/login")
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    if status_filter == "הכל":
        cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    else:
        cur.execute("SELECT * FROM reports WHERE status = %s ORDER BY timestamp DESC", (status_filter,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    table_rows = ""
    for r in rows:
        st = r['status']
        st_color = "#ff4d4d" if st == "טרם טופל" else "#ffa502" if st == "בטיפול" else "#2ed573"
        
        # FIXED IMAGE LINK: Points to our proxy route instead of FB directly
        img_cell = f'<a href="/view_image?url={r["image_url"]}" target="_blank" style="color:#764ba2; font-weight:bold; text-decoration:none;">🖼️ צפה</a>' if r.get("image_url") else '<span style="color:#ccc;">אין</span>'
        
        table_rows += f"""
        <tr>
            <td>#{r['id']}</td>
            <td><b>{r['location']}</b></td>
            <td>{r['description']}</td>
            <td>{img_cell}</td>
            <td><span style="background:{st_color}22; color:{st_color}; padding:6px 12px; border-radius:15px; font-size:12px; font-weight:bold;">{st}</span></td>
            <td>
                <div style="display:flex; gap:8px;">
                    <form action="/update_status/{r['id']}/בטיפול" method="post" style="margin:0;"><button style="background:#ffa502; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px;">בטיפול</button></form>
                    <form action="/update_status/{r['id']}/טופל" method="post" style="margin:0;"><button style="background:#2ed573; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px;">טופל</button></form>
                    <form action="/delete_report/{r['id']}" method="post" style="margin:0;" onsubmit="return confirm('למחוק תקלה זו?');"><button style="background:#e74c3c; color:white; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px;">🗑️</button></form>
                </div>
            </td>
            <td style="font-size:12px; color:#888;">{r['timestamp'].strftime('%H:%M | %d/%m') if r['timestamp'] else '-'}</td>
        </tr>"""

    return f"""
    <html><head><meta charset="UTF-8"><style>
        body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: #f4f7f6; margin: 0; padding: 30px; }}
        .header {{ background: #34495e; color: white; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; border-radius: 12px 12px 0 0; }}
        .filter-bar {{ background: white; padding: 15px 30px; display: flex; gap: 10px; border-bottom: 1px solid #eee; align-items: center; }}
        .filter-btn {{ text-decoration: none; padding: 8px 16px; border-radius: 8px; background: #f0f2f5; color: #555; font-size: 13px; font-weight: 600; }}
        .active {{ background: #764ba2; color: white; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 0 0 12px 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
        th {{ background: #fdfdfd; padding: 18px; text-align: right; border-bottom: 2px solid #eee; color: #7f8c8d; font-size: 13px; }}
        td {{ padding: 18px; border-bottom: 1px solid #f1f1f1; color: #2c3e50; }}
    </style></head><body>
    <div class="header"><h2 style="margin:0;">🏢 ניהול תקלות</h2><a href="/logout" style="color:white; text-decoration:none; font-weight:bold;">התנתקות</a></div>
    <div class="filter-bar">
        <span style="margin-left:10px; font-weight:bold; color:#7f8c8d;">סינון סטטוס:</span>
        <a href="/reports?status_filter=הכל" class="filter-btn {'active' if status_filter=='הכל' else ''}">הכל</a>
        <a href="/reports?status_filter=טרם טופל" class="filter-btn {'active' if status_filter=='טרם טופל' else ''}">טרם טופל</a>
        <a href="/reports?status_filter=בטיפול" class="filter-btn {'active' if status_filter=='בטיפול' else ''}">בטיפול</a>
        <a href="/reports?status_filter=טופל" class="filter-btn {'active' if status_filter=='טופל' else ''}">טופל</a>
    </div>
    <table>
        <thead><tr><th>ID</th><th>מיקום</th><th>תיאור</th><th>תמונה</th><th>סטטוס</th><th>עדכון</th><th>זמן דיווח</th></tr></thead>
        <tbody>{table_rows}</tbody>
    </table></body></html>
    """

@app.get("/logout")
async def logout():
    res = RedirectResponse(url="/login", status_code=303)
    res.delete_cookie("admin_session")
    return res

# --- WHATSAPP WEBHOOK ---
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
            text = msg.get("text", {}).get("body", "").strip() if msg_type == "text" else ""

            conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback(); return Response(status_code=200)

            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            if not state or text.lower() in ["היי", "hi", "תפריט", "שלום"]:
                menu = "שלום! איפה התקלה?\n1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n4. חניון\n5. חדר אשפה\n6. לובי קומתי\n7. פנים דירה\n8. גינה"
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL, sub_location=NULL, description=NULL", (phone,))
                conn.commit(); send_msg(phone, menu)

            elif state['step'] == 'LOC':
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"חניון", "5":"חדר אשפה", "6":"לובי קומתי", "7":"פנים דירה", "8":"גינה"}
                if text in locs:
                    sel_loc = locs[text]
                    cur.execute("SELECT description FROM reports WHERE location LIKE %s AND status != 'טופל' ORDER BY timestamp DESC LIMIT 1", (f"{sel_loc}%",))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute("UPDATE user_session_state SET step='CHECK_DUPLICATE', location=%s WHERE phone=%s", (sel_loc, phone))
                        conn.commit()
                        send_msg(phone, f"כבר דווחה תקלה ב{sel_loc}: '{existing['description']}'.\n\nהאם מדובר בתקלה זהה?\n1. כן\n2. לא")
                    else:
                        process_location_flow(phone, sel_loc, cur, conn)
                else: send_msg(phone, "אנא בחר מספר מהרשימה (1-8)")

            elif state['step'] == 'CHECK_DUPLICATE':
                if text == "1":
                    cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                    conn.commit(); send_msg(phone, "תודה על העדכון! הדיווח נסגר.")
                elif text == "2":
                    process_location_flow(phone, state['location'], cur, conn)
                else: send_msg(phone, "אנא בחר 1 או 2")

            elif state['step'] in ['WAIT_FLOOR', 'WAIT_APT']:
                cur.execute("UPDATE user_session_state SET step='DESC', sub_location=%s WHERE phone=%s", (text, phone))
                conn.commit(); send_msg(phone, "המיקום עודכן. כעת, תאר בבקשה את התקלה:")

            elif state['step'] == 'DESC':
                cur.execute("UPDATE user_session_state SET step='WAIT_IMAGE', description=%s WHERE phone=%s", (text, phone))
                conn.commit(); send_msg(phone, "התיאור נשמר. האם תרצה להוסיף תמונה? (שלח תמונה או שלח 'לא' לדילוג)")

            elif state['step'] == 'WAIT_IMAGE':
                img_url = get_media_url(msg["image"]["id"]) if msg_type == "image" else None
                loc_str = f"{state['location']} ({state['sub_location']})" if state['sub_location'] else state['location']
                cur.execute("INSERT INTO reports (phone, location, description, image_url, status) VALUES (%s, %s, %s, %s, 'טרם טופל')", 
                           (phone, loc_str, state['description'], img_url))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit(); send_msg(phone, "תודה! התקלה נקלטה במערכת ותטופל בהקדם. ✨")

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
