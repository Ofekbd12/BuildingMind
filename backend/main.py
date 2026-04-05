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

def get_db_connection():
    return psycopg2.connect(DB_URL)

def send_msg(to, text):
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    try: requests.post(url, json=payload, headers=headers)
    except: pass

def get_media_url(media_id):
    try:
        url = f"https://graph.facebook.com/v22.0/{media_id}"
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        res = requests.get(url, headers=headers).json()
        return res.get("url")
    except: return None

# --- HELPER: ROUTING LOGIC ---
def process_location_flow(phone, location, cur, conn):
    """
    Determines the next step based on the selected location.
    If 'Apartment' or 'Floor Lobby', asks for sub-location. Otherwise, asks for description.
    """
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
            
            # Extract text or caption
            text = ""
            if msg_type == "text":
                text = msg.get("text", {}).get("body", "").strip()
            elif msg_type == "image":
                text = msg.get("image", {}).get("caption", "").strip()
            
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Step 1: Prevent duplicate message processing from WhatsApp Webhook
            try:
                cur.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                conn.commit()
            except:
                conn.rollback()
                return Response(status_code=200)

            # Step 2: Check current user session state
            cur.execute("SELECT * FROM user_session_state WHERE phone = %s", (phone,))
            state = cur.fetchone()

            # --- FLOW 0: Initial greeting / Reset ---
            if not state or text.lower() in ["היי", "hi", "תפריט", "שלום"]:
                menu = (
                    "שלום! איפה התקלה?\n"
                    "1. לובי\n2. מעלית גדולה\n3. מעלית קטנה\n"
                    "4. חניון\n5. חדר אשפה\n6. לובי קומתי\n"
                    "7. פנים דירה\n8. גינה"
                )
                cur.execute(
                    "INSERT INTO user_session_state (phone, step) VALUES (%s, 'LOC') "
                    "ON CONFLICT (phone) DO UPDATE SET step='LOC', location=NULL, sub_location=NULL, description=NULL", 
                    (phone,)
                )
                conn.commit()
                send_msg(phone, menu)

            # --- FLOW 1: Location selection & Duplicate check ---
            elif state['step'] == 'LOC':
                locs = {
                    "1":"לובי", "2":"מעלית גדולה", "3":"מעלית קטנה", 
                    "4":"חניון", "5":"חדר אשפה", "6":"לובי קומתי", 
                    "7":"פנים דירה", "8":"גינה"
                }
                if text in locs:
                    selected_loc = locs[text]
                    # Check if there's an open issue in this specific location
                    cur.execute(
                        "SELECT description FROM reports WHERE location = %s AND status != 'טופל' "
                        "ORDER BY timestamp DESC LIMIT 1", (selected_loc,)
                    )
                    existing_issue = cur.fetchone()
                    
                    if existing_issue:
                        cur.execute("UPDATE user_session_state SET step='CHECK_DUPLICATE', location=%s WHERE phone=%s", (selected_loc, phone))
                        conn.commit()
                        send_msg(phone, f"שים לב, כבר דווחה תקלה ב{selected_loc}: '{existing_issue['description']}'.\n\nהאם מדובר בתקלה זהה?\n1. כן (סגור דיווח)\n2. לא (המשך בדיווח חדש)")
                    else:
                        process_location_flow(phone, selected_loc, cur, conn)
                else:
                    send_msg(phone, "אנא בחר מספר מהרשימה (1-8)")

            # --- FLOW 2: Handle Duplicate Confirmation ---
            elif state['step'] == 'CHECK_DUPLICATE':
                if text == "1": # Duplicate confirmed
                    cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                    conn.commit()
                    send_msg(phone, "תודה על העדכון! הדיווח נסגר כדי למנוע כפילויות.")
                elif text == "2": # New issue
                    process_location_flow(phone, state['location'], cur, conn)
                else:
                    send_msg(phone, "אנא בחר 1 (כן) או 2 (לא)")

            # --- FLOW 3: Capture Floor / Apartment ---
            elif state['step'] in ['WAIT_FLOOR', 'WAIT_APT']:
                cur.execute("UPDATE user_session_state SET step='DESC', sub_location=%s WHERE phone=%s", (text, phone))
                conn.commit()
                send_msg(phone, "המיקום עודכן. כעת, תאר בבקשה את התקלה:")

            # --- FLOW 4: Capture Description ---
            elif state['step'] == 'DESC':
                cur.execute("UPDATE user_session_state SET step='WAIT_IMAGE', description=%s WHERE phone=%s", (text, phone))
                conn.commit()
                send_msg(phone, "התיאור נשמר. האם תרצה להוסיף תמונה? (שלח תמונה כעת או שלח 'לא' לדילוג)")

            # --- FLOW 5: Capture Image and Finalize ---
            elif state['step'] == 'WAIT_IMAGE':
                img_url = None
                if msg_type == "image":
                    img_url = get_media_url(msg["image"]["id"])
                
                # Construct full location string
                sub_info = f" ({state['sub_location']})" if state.get('sub_location') else ""
                final_location = f"{state['location']}{sub_info}"
                
                # Save to reports table
                cur.execute(
                    "INSERT INTO reports (phone, location, description, image_url, status) "
                    "VALUES (%s, %s, %s, %s, 'טרם טופל')", 
                    (phone, final_location, state['description'], img_url)
                )
                # Clear session state
                cur.execute("DELETE FROM user_session_state WHERE phone=%s", (phone,))
                conn.commit()
                send_msg(phone, "תודה! התקלה נקלטה במערכת ותטופל בהקדם. ✨")

            cur.close()
            conn.close()
    except Exception as e:
        print(f"Error: {e}")
    return Response(status_code=200)

# (UI and Auth routes remain the same)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
