import os
import requests
import psycopg2
import time
import datetime
from fastapi import FastAPI, Request, Response, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import uvicorn

load_dotenv()

app = FastAPI()

# --- CONFIGURATION ---
# וודא שהשמות האלו תואמים למה שהזנת ב-Environment Variables ב-Render
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = "v22.0"
DB_URL = os.getenv("DATABASE_URL")
IMAGE_UPLOAD_DIR = "/app/uploaded_images"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")
VERIFY_TOKEN = "12345" # הטוקן שצריך להזין ב-Meta

# --- DATABASE SETUP ---
def init_db():
    for i in range(10): 
        try:
            conn = psycopg2.connect(DB_URL)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id SERIAL PRIMARY KEY,
                    phone TEXT,
                    location TEXT,
                    floor TEXT,
                    apartment TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'טרם טופל',
                    image_path TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            cursor.close()
            conn.close()
            if not os.path.exists(IMAGE_UPLOAD_DIR):
                os.makedirs(IMAGE_UPLOAD_DIR)
            print("Successfully connected to PostgreSQL.")
            break
        except Exception as e:
            print(f"Database not ready... {e}")
            time.sleep(3)

init_db()

# הגשת קבצים סטטיים (תמונות)
app.mount("/images", StaticFiles(directory=IMAGE_UPLOAD_DIR), name="images")

user_states = {}

# --- ROUTES ---

@app.get("/")
async def root():
    """הפניה אוטומטית של דף הבית לדף הלוגין"""
    return RedirectResponse(url="/login")

# --- HELPER FUNCTIONS ---

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error sending WhatsApp: {e}")

def download_whatsapp_image(media_id, user_phone):
    try:
        url_get_media = f"https://graph.facebook.com/{VERSION}/{media_id}"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        response_media = requests.get(url_get_media, headers=headers)
        if response_media.status_code != 200: return None
        image_url = response_media.json().get("url")
        response_image = requests.get(image_url, headers=headers)
        filename = f"{user_phone}_{media_id}.jpg"
        filepath = os.path.join(IMAGE_UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(response_image.content)
        return filename
    except:
        return None

# --- ADMIN AUTH & LOGIN UI ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #e74c3c; font-size: 14px;">סיסמה שגויה, נסה שוב</p>' if error else ""
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
            .login-container {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 400px; text-align: center; }}
            .logo {{ font-size: 28px; font-weight: bold; color: #4a148c; margin-bottom: 5px; }}
            .address {{ color: #666; margin-bottom: 30px; font-size: 16px; }}
            input[type="password"] {{ width: 100%; padding: 12px; margin-bottom: 20px; border: 2px solid #eee; border-radius: 8px; font-size: 16px; transition: border-color 0.3s; outline: none; box-sizing: border-box; }}
            input[type="password"]:focus {{ border-color: #764ba2; }}
            button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 8px; font-size: 18px; font-weight: bold; cursor: pointer; transition: transform 0.2s, background 0.3s; }}
            button:hover {{ background: #5a3a7e; transform: translateY(-2px); }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">MindBuilding</div>
            <div class="address">התזמורת 38</div>
            <h2 style="margin-bottom: 20px; color: #333;">כניסת מנהל 🏢</h2>
            <form action="/auth" method="post">
                <input type="password" name="password" placeholder="הקש סיסמה לניהול" required>
                {error_msg}
                <button type="submit">התחבר למערכת</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/reports", status_code=302)
        response.set_cookie(key="admin_session", value="authenticated", max_age=86400)
        return response
    return RedirectResponse(url="/login?error=True", status_code=302)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("admin_session")
    return response

# --- PROTECTED ADMIN ROUTES ---

@app.get("/reports", response_class=HTMLResponse)
async def show_reports(request: Request, sort_by: str = "timestamp"):
    if request.cookies.get("admin_session") != "authenticated":
        return RedirectResponse(url="/login")

    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        order_clause = "ORDER BY timestamp DESC"
        if sort_by == "status":
            order_clause = "ORDER BY status DESC, timestamp DESC"
        
        cursor.execute(f"SELECT id, phone, location, floor, apartment, description, status, image_path, timestamp FROM reports {order_clause}")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; padding: 20px; background-color: #f4f7f6; }}
                .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.08); max-width: 1200px; margin: auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 15px; margin-bottom: 20px; }}
                .title {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
                table {{ border-collapse: collapse; width: 100%; background: white; }}
                th, td {{ border: 1px solid #edf2f7; text-align: right; padding: 15px; }}
                th {{ background-color: #4a5568; color: white; }}
                .btn {{ text-decoration: none; padding: 6px 12px; color: white; border-radius: 5px; font-size: 12px; font-weight: bold; display: inline-block; }}
                .status-tag {{ font-weight: bold; padding: 5px 10px; border-radius: 20px; font-size: 12px; }}
                .status-pending {{ background: #fed7d7; color: #c53030; }}
                .report-img {{ max-width: 60px; border-radius: 6px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <div class="title">MindBuilding - התזמורת 38 🏢</div>
                    <a href="/logout" style="color:red; text-decoration:none;">התנתק</a>
                </div>
                <table>
                    <tr><th>ID</th><th>מיקום</th><th>דירה/קומה</th><th>תיאור</th><th>תמונה</th><th>סטטוס</th><th>פעולות</th></tr>
        """
        for row in rows:
            img_html = f"<a href='/images/{row[7]}' target='_blank'><img class='report-img' src='/images/{row[7]}'></a>" if row[7] else "-"
            html += f"""
            <tr>
                <td>{row[0]}</td>
                <td><b>{row[2]}</b></td>
                <td>דירה {row[4]} (ק' {row[3]})</td>
                <td>{row[5]}</td>
                <td>{img_html}</td>
                <td>{row[6]}</td>
                <td>
                    <a class="btn" style="background:#f6ad55" href="/update_status/{row[0]}/בטיפול">בטיפול</a>
                    <a class="btn" style="background:#48bb78" href="/update_status/{row[0]}/טופל">טופל</a>
                </td>
            </tr>"""
        html += "</table></div></body></html>"
        return Response(content=html, media_type="text/html")
    except Exception as e:
        return Response(content=f"Error: {str(e)}", status_code=500)

@app.get("/update_status/{{report_id}}/{{new_status}}")
async def update_report_status(request: Request, report_id: int, new_status: str):
    if request.cookies.get("admin_session") != "authenticated":
        return RedirectResponse(url="/login")
    
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("UPDATE reports SET status = %s WHERE id = %s RETURNING phone, location, description", (new_status, report_id))
        row = cursor.fetchone()
        conn.commit()
        if row and new_status == "טופל":
            send_whatsapp_message(row[0], f"התקלה ב-{row[1]} ({row[2]}) טופלה! ✨")
        cursor.close()
        conn.close()
        return RedirectResponse(url="/reports")
    except:
        return RedirectResponse(url="/reports")

# --- WHATSAPP WEBHOOK ---

@app.post("/whatsapp")
async def handle_whatsapp_webhook(request: Request):
    data = await request.json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            user_phone = message["from"]
            user_text = message.get("text", {}).get("body", "").strip()
            user_image_id = message.get("image", {}).get("id")
            
            now = datetime.datetime.now()

            if user_phone in user_states:
                last_seen = user_states[user_phone].get("last_seen")
                if last_seen and (now - last_seen).total_seconds() > 180:
                    del user_states[user_phone]

            if user_phone not in user_states:
                user_states[user_phone] = {"step": "SELECT_LOCATION", "last_seen": now}
                response_text = "שלום! איפה קרתה התקלה?\n1. לובי\n2. מעלית\n3. חניון\n4. אחר"
            else:
                user_states[user_phone]["last_seen"] = now
                step = user_states[user_phone]["step"]

                if step == "SELECT_LOCATION":
                    user_states[user_phone]["location"] = user_text
                    user_states[user_phone]["step"] = "GET_DESCRIPTION"
                    response_text = "תאר את התקלה:"
                elif step == "GET_DESCRIPTION":
                    user_states[user_phone]["description"] = user_text
                    user_states[user_phone]["step"] = "GET_IMAGE"
                    response_text = "שלח תמונה או כתוב 'אין':"
                elif step == "GET_IMAGE":
                    img_file = download_whatsapp_image(user_image_id, user_phone) if user_image_id else None
                    conn = psycopg2.connect(DB_URL)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO reports (phone, location, description, image_path) VALUES (%s, %s, %s, %s)",
                        (user_phone, user_states[user_phone]["location"], user_states[user_phone]["description"], img_file)
                    )
                    conn.commit()
                    cursor.close()
                    conn.close()
                    response_text = "תודה! הדיווח התקבל."
                    del user_states[user_phone]

            send_whatsapp_message(user_phone, response_text)
    except: pass
    return Response(status_code=200)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
