"""
M-Changia WhatsApp Fundraiser Bot
Main Flask Application Entry Point
"""

import logging
from flask import Flask, request, jsonify
from config import Config
from models import db
from services.bot_handler import handle_message, handle_mpesa_callback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

with app.app_context():
    db.create_all()
    logger.info("✅ Database tables created.")


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return jsonify({
        'app': 'M-Changia',
        'tagline': 'Automated WhatsApp Fundraiser Tracker',
        'status': 'running',
        'version': '1.0.0'
    })


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200


@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Receives incoming WhatsApp messages from Africa's Talking.
    Africa's Talking sends a POST with JSON payload to this URL.
    """
    try:
        # Accept both JSON and form-encoded payloads
        data = request.get_json(silent=True) or request.form.to_dict()
        logger.info(f"📩 Incoming WhatsApp webhook: {data}")

        result = handle_message(data)
        return jsonify({'status': 'ok', 'result': result}), 200

    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/webhook/mpesa', methods=['POST'])
def mpesa_callback():
    """
    Receives M-Pesa STK Push payment callbacks from Safaricom Daraja.
    Called automatically by Safaricom after the user pays (or cancels).
    """
    try:
        data = request.get_json(silent=True)
        logger.info(f"💳 M-Pesa callback received: {data}")

        result = handle_mpesa_callback(data)
        # Safaricom expects this exact response format
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Success'}), 200

    except Exception as e:
        logger.error(f"❌ M-Pesa callback error: {str(e)}", exc_info=True)
        return jsonify({'ResultCode': 1, 'ResultDesc': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
