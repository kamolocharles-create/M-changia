"""
M-Changia WhatsApp Service
Handles all outgoing messages via Africa's Talking WhatsApp API,
and parses incoming webhook payloads.
"""

import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

AT_WHATSAPP_URL = "https://chat.africastalking.com/whatsapp/message"


# ──────────────────────────────────────────────────────────────
# OUTGOING MESSAGES
# ──────────────────────────────────────────────────────────────

def send_message(to_phone: str, message: str) -> bool:
    """
    Send a WhatsApp message to a phone number.
    to_phone should be in any Kenyan format — we'll normalize it.
    Returns True on success, False on failure.
    """
    try:
        phone = normalize_phone(to_phone)

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'apiKey': Config.AT_API_KEY,
        }
        payload = {
            "username": Config.AT_USERNAME,
            "to": phone,
            "message": message,
            "from": Config.AT_WHATSAPP_SENDER,
        }

        response = requests.post(AT_WHATSAPP_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        logger.info(f"✅ Message sent to {phone} | Status: {response.status_code}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send message to {to_phone}: {str(e)}")
        return False


# ──────────────────────────────────────────────────────────────
# INCOMING WEBHOOK PARSER
# ──────────────────────────────────────────────────────────────

def parse_webhook(data: dict) -> dict:
    """
    Normalize Africa's Talking incoming WhatsApp webhook payload.

    AT sends different structures depending on message type.
    We normalize to: { 'from': phone, 'text': message_text, 'id': msg_id }

    We also log the raw payload so you can inspect it during setup
    and adjust if AT changes their format.
    """
    logger.debug(f"Raw webhook payload: {data}")

    result = {'from': '', 'text': '', 'id': ''}

    if not data:
        return result

    try:
        # ── Format 1: Nested under 'data' key ──────────────────
        if 'data' in data and isinstance(data['data'], dict):
            inner = data['data']
            result['from'] = (
                inner.get('from', {}).get('number', '')
                or inner.get('from', '')
            )
            msg = inner.get('message', {})
            result['text'] = msg.get('text', '') if isinstance(msg, dict) else str(msg)
            result['id'] = inner.get('id', '')
            return result

        # ── Format 2: Flat structure ────────────────────────────
        if 'from' in data:
            result['from'] = data.get('from', '')
            result['text'] = (
                data.get('text')
                or data.get('message')
                or data.get('body', '')
            )
            result['id'] = data.get('id', data.get('messageId', ''))
            return result

        # ── Format 3: Africa's Talking form-encoded ─────────────
        if 'phoneNumber' in data:
            result['from'] = data.get('phoneNumber', '')
            result['text'] = data.get('text', '')
            result['id'] = data.get('id', '')
            return result

        logger.warning(f"⚠️ Unrecognised webhook format: {list(data.keys())}")

    except Exception as e:
        logger.error(f"Error parsing webhook: {str(e)}")

    return result


# ──────────────────────────────────────────────────────────────
# PHONE UTILITIES
# ──────────────────────────────────────────────────────────────

def normalize_phone(phone: str) -> str:
    """
    Normalize any Kenyan phone number to 2547XXXXXXXX format.

    Handles:
      07XXXXXXXX  →  2547XXXXXXXX
      01XXXXXXXX  →  2541XXXXXXXX
      +2547XXXXXXXX  →  2547XXXXXXXX
      whatsapp:+2547XXXXXXXX  →  2547XXXXXXXX
    """
    phone = str(phone).strip()
    phone = phone.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')

    if phone.startswith('07') or phone.startswith('01'):
        phone = '254' + phone[1:]

    if not phone.startswith('254'):
        phone = '254' + phone

    return phone
