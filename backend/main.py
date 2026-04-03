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
    error_msg = '<p style="color: red;">Wrong password</p>' if error else ""
    return f"""
    <html><body style="font-family:sans-serif; text-align:center; padding-top:100px; direction:rtl;">
        <h2>כניסת ניהול - ועד הבית</h2>
        <form action="/auth" method="post">
            <input type="password" name="password" placeholder="סיסמה" required>
            {error_msg}<br><br>
            <button type="submit">התחבר</button>
        </form>
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
    # Get all reports
    cur.execute("SELECT * FROM reports ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    table_rows = ""
    for r in rows:
        table_rows += f"""
        <tr>
            <td>{r['id']}</td>
            <td>{r['location']}</td>
            <td>{r['description']}</td>
            <td>{r['status']}</td>
            <td>{r['timestamp'].strftime('%d/%m %H:%M')}</td>
        </tr>
        """
    
    return f"""
    <html><body style="font-family:sans-serif; direction:rtl; padding:20px;">
        <h2>דו"ח תקלות - התזמורת 38</h2>
        <table border="1" style="width:100%; border-collapse:collapse; text-align:right;">
            <tr style="background:#eee;">
                <th>ID</th><th>מיקום</th><th>תיאור</th><th>סטטוס</th><th>זמן</th>
            </tr>
            {table_rows}
        </table>
        <br><a href="/logout">התנתק</a>
    </body></html>
    """

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

# --- WHATSAPP BOT LOGIC ---

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

            # 2. Get/Update State from DB
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (user_phone,))
            state = cur.fetchone()
            cur.close()
            conn.close()

            if not state or user_text.lower() in ['היי', 'hi', 'start', 'ביטול']:
                # Reset/Start session
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO user_session_state (phone, step) VALUES (%s, 'SELECT_LOCATION') ON CONFLICT (phone) DO UPDATE SET step='SELECT_LOCATION'", (user_phone,))
                conn.commit()
                cur.close()
                conn.close()
                
                msg = "שלום! איפה התקלה?\n1. לובי\n2. מעלית\n3. חניון\n4. גינה\n5. אחר"
                send_whatsapp_message(user_phone, msg)

            elif state['step'] == 'SELECT_LOCATION':
                locs = {"1":"לובי", "2":"מעלית", "3":"חניון", "4":"גינה", "5":"אחר"}
                loc_name = locs.get(user_text, "אחר")
                
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("UPDATE user_session_state SET step='GET_DESC', location=%s WHERE phone=%s", (loc_name, user_phone))
                conn.commit()
                cur.close()
                conn.close()
                
                send_whatsapp_message(user_phone, f"נבחר: {loc_name}. תאר בקצרה את התקלה:")

            elif state['step'] == 'GET_DESC':
                # Final save to reports
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO reports (phone, location, description) VALUES (%s, %s, %s)", (user_phone, state['location'], user_text))
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (user_phone,))
                conn.commit()
                cur.close()
                conn.close()
                
                send_whatsapp_message(user_phone, "תודה! הדיווח נשמר.")

    except Exception as e:
        print(f"Error: {e}")
    return Response(status_code=200)

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, json=payload, headers=headers)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "12345":
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
