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

# --- DB STATE HELPERS (The "Persistence" Logic) ---

def get_user_state(phone):
    """Fetches the current step of the resident from DB"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
    state = cur.fetchone()
    cur.close()
    conn.close()
    return state

def update_user_state(phone, step, data=None):
    """Saves the resident's progress so it won't be lost on Restart"""
    if data is None: data = {}
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_session_state (phone, step, location, floor, apartment, description, last_interaction)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (phone) DO UPDATE SET 
            step = EXCLUDED.step,
            location = COALESCE(EXCLUDED.location, user_session_state.location),
            floor = COALESCE(EXCLUDED.floor, user_session_state.floor),
            apartment = COALESCE(EXCLUDED.apartment, user_session_state.apartment),
            description = COALESCE(EXCLUDED.description, user_session_state.description),
            last_interaction = CURRENT_TIMESTAMP
    """, (phone, step, data.get('location'), data.get('floor'), data.get('apartment'), data.get('description')))
    conn.commit()
    cur.close()
    conn.close()

def delete_user_state(phone):
    """Clears the session when the report is finished"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_session_state WHERE phone = %s", (phone,))
    conn.commit()
    cur.close()
    conn.close()

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, json=payload, headers=headers)

# --- WHATSAPP WEBHOOK ---

@app.post("/whatsapp")
async def handle_whatsapp(request: Request):
    data = await request.json()
    try:
        if "messages" in data["entry"][0]["changes"][0]["value"]:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            msg_id = message["id"]
            user_phone = message["from"]
            user_text = message.get("text", {}).get("body", "").strip()

            # 1. Deduplication (Prevents 3x menus during Cold Start)
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback()
                return Response(status_code=200) # Already handled
            finally:
                cur.close()
                conn.close()

            # 2. Retrieve state from DB (Persistent Memory)
            state = get_user_state(user_phone)

            # 3. Decision Tree
            if not state or user_text.lower() in ['היי', 'hi', 'start', 'ביטול']:
                update_user_state(user_phone, "SELECT_LOCATION")
                msg = ("שלום! איפה קרתה התקלה?\n"
                       "1. לובי 🏢\n2. מעלית גדולה 🛗\n3. מעלית קטנה 🛗\n"
                       "4. פח אשפה 🗑️\n5. חניון 🚗\n6. גינה 🌳\n"
                       "7. לובי קומתי 🏠\n8. פנים דירה 🔑")
                send_whatsapp_message(user_phone, msg)
            
            elif state['step'] == "SELECT_LOCATION":
                locs = {"1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", "4":"פח אשפה", "5":"חניון", "6":"גינה", "7":"לובי קומתי", "8":"פנים דירה"}
                if user_text in locs:
                    loc_name = locs[user_text]
                    if user_text == "7":
                        update_user_state(user_phone, "GET_FLOOR", {"location": loc_name})
                        send_whatsapp_message(user_phone, "באיזו קומה?")
                    elif user_text == "8":
                        update_user_state(user_phone, "GET_APARTMENT", {"location": loc_name})
                        send_whatsapp_message(user_phone, "באיזו דירה?")
                    else:
                        update_user_state(user_phone, "GET_DESCRIPTION", {"location": loc_name})
                        send_whatsapp_message(user_phone, "תאר בקצרה את התקלה:")
                else:
                    send_whatsapp_message(user_phone, "נא לבחור מספר 1-8.")

            elif state['step'] == "GET_FLOOR":
                update_user_state(user_phone, "GET_DESCRIPTION", {"floor": user_text})
                send_whatsapp_message(user_phone, "תאר בקצרה את התקלה:")

            elif state['step'] == "GET_APARTMENT":
                update_user_state(user_phone, "GET_DESCRIPTION", {"apartment": user_text})
                send_whatsapp_message(user_phone, "תאר בקצרה את התקלה:")

            elif state['step'] == "GET_DESCRIPTION":
                # Final save to reports table
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO reports (phone, location, floor, apartment, description) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_phone, state['location'], state.get('floor','N/A'), state.get('apartment','N/A'), user_text))
                conn.commit()
                cur.close()
                conn.close()
                
                send_whatsapp_message(user_phone, "תודה! הדיווח התקבל ויועבר לטיפול. ✨")
                delete_user_state(user_phone) # Clear session

    except Exception as e:
        print(f"Error in Webhook: {e}")
    return Response(status_code=200)

@app.get("/whatsapp")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "12345":
        return Response(content=request.query_params.get("hub.challenge"))
    return Response(status_code=403)

# --- ADD YOUR ADMIN/LOGIN/REPORTS ROUTES HERE ---
