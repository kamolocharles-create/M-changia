"""
M-Changia M-Pesa Service
Handles Safaricom Daraja API interactions:
  - OAuth token generation
  - STK Push (send payment prompt to phone)
"""

import base64
import logging
import requests
from datetime import datetime
from config import Config
from models import db, MpesaTransaction
from services.whatsapp_service import normalize_phone

logger = logging.getLogger(__name__)


def _base_url() -> str:
    if Config.DARAJA_ENV == 'production':
        return 'https://api.safaricom.co.ke'
    return 'https://sandbox.safaricom.co.ke'


def _get_access_token() -> str:
    """Fetches a fresh OAuth token from Daraja. Valid for 1 hour."""
    try:
        credentials = base64.b64encode(
            f"{Config.DARAJA_CONSUMER_KEY}:{Config.DARAJA_CONSUMER_SECRET}".encode()
        ).decode()

        response = requests.get(
            f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
            headers={'Authorization': f'Basic {credentials}'},
            timeout=30
        )
        response.raise_for_status()
        token = response.json().get('access_token', '')
        logger.info("✅ Daraja access token obtained.")
        return token

    except Exception as e:
        logger.error(f"❌ Failed to get Daraja token: {str(e)}")
        return ''


def initiate_stk_push(
    phone: str,
    amount: int,
    account_reference: str,
    description: str,
    fundraiser_id: int
) -> dict:
    """
    Sends an M-Pesa STK Push request to the treasurer's phone.
    The treasurer sees a payment prompt and enters their PIN.

    Returns:
        {'success': True, 'checkout_request_id': '...'} on success
        {'success': False, 'error': '...'} on failure
    """
    try:
        token = _get_access_token()
        if not token:
            return {'success': False, 'error': 'Could not authenticate with Daraja'}

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        shortcode = Config.DARAJA_SHORTCODE
        passkey = Config.DARAJA_PASSKEY

        # Daraja password = base64(shortcode + passkey + timestamp)
        password = base64.b64encode(
            f"{shortcode}{passkey}{timestamp}".encode()
        ).decode()

        phone = normalize_phone(phone)

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": max(1, int(amount)),
            "PartyA": phone,
            "PartyB": shortcode,
            "PhoneNumber": phone,
            "CallBackURL": f"{Config.BASE_URL}/webhook/mpesa",
            "AccountReference": account_reference[:12],   # Daraja max 12 chars
            "TransactionDesc": description[:13]            # Daraja max 13 chars
        }

        response = requests.post(
            f"{_base_url()}/mpesa/stkpush/v1/processrequest",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        checkout_id = result.get('CheckoutRequestID', '')

        # Persist the transaction record
        txn = MpesaTransaction(
            checkout_request_id=checkout_id,
            fundraiser_id=fundraiser_id,
            phone=phone,
            amount=amount,
            status='pending'
        )
        db.session.add(txn)
        db.session.commit()

        logger.info(f"✅ STK Push sent to {phone} for KES {amount} | ID: {checkout_id}")
        return {'success': True, 'checkout_request_id': checkout_id}

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ STK Push failed: {str(e)}")
        return {'success': False, 'error': str(e)}
