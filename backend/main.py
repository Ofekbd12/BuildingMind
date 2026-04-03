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
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = "v22.0"
DB_URL = os.getenv("DATABASE_URL")
IMAGE_UPLOAD_DIR = "/app/uploaded_images"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "vaad1234")

# --- DATABASE SETUP ---
def get_db_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    if not os.path.exists(IMAGE_UPLOAD_DIR):
        os.makedirs(IMAGE_UPLOAD_DIR)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Create reports table
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
        # Create table to prevent duplicate messages (retries)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Init DB Error: {e}")

init_db()
app.mount("/images", StaticFiles(directory=IMAGE_UPLOAD_DIR), name="images")

# In-memory dictionary to store user conversation state
user_states = {}

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
    except Exception as e:
        print(f"Image download error: {e}")
        return None

# --- ADMIN ROUTES ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: bool = False):
    error_msg = '<p style="color: #e74c3c; font-size: 14px;">Invalid password, try again</p>' if error else ""
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; margin: 0; display: flex; justify-content: center; align-items: center; }}
            .login-container {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); width: 100%; max-width: 400px; text-align: center; }}
            .logo {{ font-size: 28px; font-weight: bold; color: #4a148c; margin-bottom: 5px; }}
            input[type="password"] {{ width: 100%; padding: 12px; margin-bottom: 20px; border: 2px solid #eee; border-radius: 8px; box-sizing: border-box; text-align: center; }}
            button {{ width: 100%; padding: 12px; background: #764ba2; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">MindBuilding</div>
            <div class="address">HaTizmoret 38</div>
            <h2>Admin Login 🏢</h2>
            <form action="/auth" method="post">
                <input type="password" name="password" placeholder="Enter Password" required>
                {error_msg}
                <button type="submit">Login</button>
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

@app.get("/reports", response_class=HTMLResponse)
