"""
M-Changia Configuration
Reads all settings from environment variables (.env file)
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Flask ──────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # ── Database ───────────────────────────────────────
    # SQLite for development/MVP. Render provides PostgreSQL for production.
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///mchangia.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Africa's Talking (WhatsApp) ────────────────────
    AT_USERNAME = os.getenv('AT_USERNAME', '')
    AT_API_KEY = os.getenv('AT_API_KEY', '')
    AT_WHATSAPP_SENDER = os.getenv('AT_WHATSAPP_SENDER', '')  # Your WhatsApp business number

    # ── Safaricom Daraja (M-Pesa) ──────────────────────
    DARAJA_CONSUMER_KEY = os.getenv('DARAJA_CONSUMER_KEY', '')
    DARAJA_CONSUMER_SECRET = os.getenv('DARAJA_CONSUMER_SECRET', '')
    DARAJA_SHORTCODE = os.getenv('DARAJA_SHORTCODE', '174379')  # Default: sandbox shortcode
    DARAJA_PASSKEY = os.getenv('DARAJA_PASSKEY', '')
    DARAJA_ENV = os.getenv('DARAJA_ENV', 'sandbox')  # sandbox → production when ready

    # ── App Settings ───────────────────────────────────
    BASE_URL = os.getenv('BASE_URL', 'https://your-app.onrender.com')
    SERVICE_FEE_PER_ENTRY = int(os.getenv('SERVICE_FEE_PER_ENTRY', 5))   # KES 5 per contribution
    REPORT_FEE = int(os.getenv('REPORT_FEE', 100))                        # KES 100 for PDF report
