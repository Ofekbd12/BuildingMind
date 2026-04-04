-- 1. Main table for storing reported issues
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    phone TEXT, -- Reporter's WhatsApp number
    location TEXT, -- Selected location (Lobby, Elevator, etc.)
    floor TEXT DEFAULT '-', -- Optional floor number
    apartment TEXT DEFAULT '-', -- Optional apartment number
    description TEXT, -- Issue description provided by user
    image_url TEXT, -- URL of the image hosted by WhatsApp/Meta
    status TEXT DEFAULT 'טרם טופל', -- Current status of the report
    timestamp TIMESTAMPTZ DEFAULT NOW() -- Date and time of report
);

-- 2. Session management table for the WhatsApp bot flow
CREATE TABLE IF NOT EXISTS user_session_state (
    phone TEXT PRIMARY KEY, -- Unique user identifier (phone number)
    step TEXT, -- Current step in the conversation (LOC, FLOOR, DESC, etc.)
    location TEXT, -- Temporarily stored location during the flow
    floor TEXT, -- Temporarily stored floor
    apartment TEXT -- Temporarily stored apartment number
);

-- 3. Idempotency table to prevent duplicate processing of the same message
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY, -- Unique ID sent by Meta/WhatsApp API
    processed_at TIMESTAMPTZ DEFAULT NOW() -- Timestamp of when it was handled
);
