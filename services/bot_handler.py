"""
M-Changia Bot Handler
The brain of the bot. Manages conversation state and routes
every incoming message to the correct handler function.

States:
  idle         — No active fundraiser. Waiting for "new".
  setup_name   — Asked for fundraiser name.
  setup_target — Asked for target amount.
  active       — Fundraiser running. Ready to log contributions.
  closing      — Treasurer requested close. Waiting for payment.
"""

import logging
import random
import string
from datetime import datetime

from models import db, Fundraiser, Contribution, Session, MpesaTransaction
from services.sms_parser import parse_mpesa_sms
from services.whatsapp_service import send_message, parse_webhook, normalize_phone
from services.mpesa_service import initiate_stk_push
from services.pdf_service import generate_fundraiser_report
from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────

def _generate_code() -> str:
    """Generate a unique fundraiser code like MCH-A3F7"""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = 'MCH-' + ''.join(random.choices(chars, k=4))
        if not Fundraiser.query.filter_by(code=code).first():
            return code


def _get_session(phone: str) -> Session:
    """Get or create a conversation session for this phone number"""
    phone = normalize_phone(phone)
    session = Session.query.get(phone)
    if not session:
        session = Session(phone=phone, state='idle')
        db.session.add(session)
        db.session.commit()
    return session


def _sms(phone: str, text: str):
    """Shortcut: send a WhatsApp message"""
    send_message(phone, text)


# ──────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────

def handle_message(webhook_data: dict) -> str:
    """
    Called by app.py for every incoming WhatsApp message.
    Parses the payload, loads the session, and routes the message.
    """
    msg = parse_webhook(webhook_data)

    if not msg.get('from') or not msg.get('text'):
        logger.warning(f"⚠️ Ignored empty/unparseable webhook: {webhook_data}")
        return 'ignored'

    phone = normalize_phone(msg['from'])
    text = msg['text'].strip()
    text_lower = text.lower()

    logger.info(f"📩 [{phone}] → \"{text[:80]}\"")

    session = _get_session(phone)

    # ── Global commands (work in any state) ────────────────
    if text_lower in ['help', 'msaada', '?']:
        return _send_help(phone)

    # ── Route by conversation state ────────────────────────
    if session.state == 'idle':
        return _handle_idle(phone, text, text_lower, session)
    elif session.state == 'setup_name':
        return _handle_setup_name(phone, text, session)
    elif session.state == 'setup_target':
        return _handle_setup_target(phone, text, session)
    elif session.state == 'active':
        return _handle_active(phone, text, text_lower, session)
    elif session.state == 'closing':
        return _handle_closing(phone, text_lower, session)

    return 'unhandled'


# ──────────────────────────────────────────────────────────────
# STATE HANDLERS
# ──────────────────────────────────────────────────────────────

def _handle_idle(phone, text, text_lower, session):
    """No active fundraiser. Offer to start one."""

    # Check if it's a forwarded M-Pesa SMS with no active fundraiser
    if parse_mpesa_sms(text):
        _sms(phone,
             "⚠️ I received an M-Pesa confirmation but you have no active fundraiser.\n\n"
             "Type *new* to start one first.")
        return 'no_fundraiser'

    # Start new fundraiser
    if any(w in text_lower for w in ['new', 'start', 'mpya', 'anza', 'harambee', 'fundraiser', 'changia']):
        session.state = 'setup_name'
        db.session.commit()
        _sms(phone,
             "🎉 *Karibu M-Changia!*\n\n"
             "I will automate your fundraiser tracking — "
             "no more manual copy-pasting.\n\n"
             "📝 *Step 1 of 2*\n"
             "What is the *name* of this fundraiser?\n\n"
             "_Examples:_\n"
             "• Burial for Mama Wanjiku\n"
             "• Wedding for John & Mary\n"
             "• Medical Bill — David Otieno")
        return 'setup_started'

    # Default welcome
    _sms(phone,
         "👋 *Welcome to M-Changia!*\n\n"
         "I automate WhatsApp fundraiser tracking.\n"
         "No more manual totals. No more accounting drama.\n\n"
         "Type *new* to start your fundraiser\n"
         "Type *help* for all commands")
    return 'welcome_sent'


def _handle_setup_name(phone, text, session):
    """Save the fundraiser name, ask for target amount."""

    if len(text.strip()) < 3:
        _sms(phone, "❌ Name is too short. Please enter the fundraiser name:")
        return 'name_too_short'

    temp = session.get_temp()
    temp['name'] = text.strip()
    session.set_temp(temp)
    session.state = 'setup_target'
    db.session.commit()

    _sms(phone,
         f"✅ *Fundraiser:* {text.strip()}\n\n"
         "💰 *Step 2 of 2*\n"
         "What is your *target amount* in KES?\n\n"
         "_Examples: 50000 or 150000_")
    return 'name_saved'


def _handle_setup_target(phone, text, session):
    """Save target amount, create the fundraiser."""

    clean = text.replace(',', '').replace('KES', '').replace('Ksh', '').replace(' ', '').strip()
    try:
        target = float(clean)
        if target < 100:
            raise ValueError("Amount too small")
    except (ValueError, TypeError):
        _sms(phone, "❌ Please enter a valid amount.\n_Example: 50000_")
        return 'invalid_amount'

    temp = session.get_temp()
    fundraiser_name = temp.get('name', 'Unnamed Fundraiser')

    fundraiser = Fundraiser(
        code=_generate_code(),
        name=fundraiser_name,
        target_amount=target,
        treasurer_phone=phone,
        status='active',
    )
    db.session.add(fundraiser)
    db.session.flush()  # Get the ID before commit

    session.state = 'active'
    session.fundraiser_id = fundraiser.id
    session.set_temp({})
    db.session.commit()

    _sms(phone,
         f"🎊 *Fundraiser Created!*\n\n"
         f"📋 {fundraiser.name}\n"
         f"🎯 Target: KES {target:,.0f}\n"
         f"🔖 Code: *{fundraiser.code}*\n\n"
         f"━━━━━━━━━━━━━━━━\n"
         f"*HOW TO USE:*\n\n"
         f"When you receive an M-Pesa contribution, "
         f"simply *forward the confirmation SMS* to this number.\n\n"
         f"I'll log it instantly and send you a formatted update "
         f"to paste in your group.\n\n"
         f"━━━━━━━━━━━━━━━━\n"
         f"*COMMANDS:*\n"
         f"• *status* — current totals\n"
         f"• *contributors* — list everyone\n"
         f"• *close* — end & get PDF report\n"
         f"• *help* — all commands\n\n"
         f"_You can share this with your group:_\n"
         f"_\"Tracked by M-Changia | Code: {fundraiser.code}\"_")
    return 'fundraiser_created'


def _handle_active(phone, text, text_lower, session):
    """Fundraiser is live. Handle contributions and commands."""

    fundraiser = Fundraiser.query.get(session.fundraiser_id)
    if not fundraiser:
        session.state = 'idle'
        session.fundraiser_id = None
        db.session.commit()
        return _handle_idle(phone, text, text_lower, session)

    # Commands
    if text_lower in ['status', 'hali', 'total']:
        return _send_status(phone, fundraiser)

    if text_lower in ['contributors', 'list', 'orodha', 'wote']:
        return _send_contributors(phone, fundraiser)

    if text_lower in ['close', 'end', 'maliza', 'funga']:
        return _initiate_close(phone, fundraiser, session)

    if text_lower in ['help', '?', 'msaada']:
        return _send_help(phone)

    # Try to parse as forwarded M-Pesa SMS
    parsed = parse_mpesa_sms(text)
    if parsed:
        return _log_contribution(phone, fundraiser, parsed, text)

    # Unrecognised
    _sms(phone,
         f"🤔 I didn't understand that.\n\n"
         f"*Active:* {fundraiser.name}\n\n"
         f"Forward an M-Pesa SMS to log a contribution,\n"
         f"or type *help* for commands.")
    return 'unrecognised'


def _handle_closing(phone, text_lower, session):
    """Waiting for treasurer to confirm payment."""

    fundraiser = Fundraiser.query.get(session.fundraiser_id)

    if text_lower in ['back', 'rudi', 'cancel']:
        session.state = 'active'
        db.session.commit()
        _sms(phone, f"✅ *{fundraiser.name}* is still active. Keep going!")
        return 'back_to_active'

    if text_lower in ['pay', 'lipa', 'yes', 'ndio', 'ok']:
        return _send_stk_push(phone, fundraiser)

    _sms(phone,
         "Type *pay* to receive the M-Pesa payment request,\n"
         "or *back* to continue the fundraiser.")
    return 'awaiting_payment_decision'


# ──────────────────────────────────────────────────────────────
# CONTRIBUTION LOGGING
# ──────────────────────────────────────────────────────────────

def _log_contribution(phone, fundraiser, parsed, raw_text):
    """Log a single verified contribution to the fundraiser."""

    # Duplicate check by M-Pesa ref
    if parsed.mpesa_ref != 'N/A':
        existing = Contribution.query.filter_by(
            fundraiser_id=fundraiser.id,
            mpesa_ref=parsed.mpesa_ref
        ).first()
        if existing:
            _sms(phone, f"⚠️ This transaction ({parsed.mpesa_ref}) was already logged.")
            return 'duplicate'

    contribution = Contribution(
        fundraiser_id=fundraiser.id,
        contributor_name=parsed.sender_name,
        contributor_phone=parsed.sender_phone,
        amount=parsed.amount,
        mpesa_ref=parsed.mpesa_ref,
        raw_sms=raw_text,
    )
    db.session.add(contribution)
    db.session.commit()

    # Reload fundraiser to get updated totals
    db.session.refresh(fundraiser)

    remaining = max(0, fundraiser.target_amount - fundraiser.total_raised)
    target_hit = fundraiser.total_raised >= fundraiser.target_amount

    update = (
        f"🎉 *Contribution Confirmed!*\n\n"
        f"👤 *{parsed.sender_name}* — KES {parsed.amount:,.0f}\n"
        f"🔖 Ref: {parsed.mpesa_ref}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 *Live Progress*\n"
        f"Raised: KES {fundraiser.total_raised:,.0f} / KES {fundraiser.target_amount:,.0f}\n"
        f"{fundraiser.progress_bar()} {fundraiser.progress_percentage:.1f}%\n"
        f"👥 {fundraiser.contributor_count} contributor{'s' if fundraiser.contributor_count != 1 else ''}\n"
    )

    if target_hit:
        update += "\n🏆 *TARGET REACHED! Thank you all!* 🎊"
    else:
        update += f"\n💡 Still needed: KES {remaining:,.0f}"

    update += f"\n\n_M-Changia | {fundraiser.name}_"

    _sms(phone, update)
    logger.info(f"✅ Logged: KES {parsed.amount} from {parsed.sender_name}")
    return 'contribution_logged'


# ──────────────────────────────────────────────────────────────
# CLOSE & BILLING
# ──────────────────────────────────────────────────────────────

def _initiate_close(phone, fundraiser, session):
    """Show closing summary and ask for payment confirmation."""

    entries = fundraiser.contributor_count
    service_fee = entries * Config.SERVICE_FEE_PER_ENTRY
    report_fee = Config.REPORT_FEE
    total_fee = service_fee + report_fee

    session.state = 'closing'
    db.session.commit()

    _sms(phone,
         f"📋 *Close Fundraiser*\n"
         f"_{fundraiser.name}_\n\n"
         f"📊 Final Summary:\n"
         f"• Total Raised: KES {fundraiser.total_raised:,.0f}\n"
         f"• Contributors: {entries}\n"
         f"• Target: KES {fundraiser.target_amount:,.0f}\n\n"
         f"━━━━━━━━━━━━━━━━\n"
         f"💳 *Service Fee Breakdown*\n"
         f"• {entries} entries × KES {Config.SERVICE_FEE_PER_ENTRY} = KES {service_fee:,.0f}\n"
         f"• Audit PDF Report = KES {report_fee:,.0f}\n"
         f"• *Total Due: KES {total_fee:,.0f}*\n\n"
         f"Type *pay* — I'll send an M-Pesa request to your phone\n"
         f"Type *back* — continue the fundraiser")
    return 'close_initiated'


def _send_stk_push(phone, fundraiser):
    """Send M-Pesa STK Push for service fee."""

    total_fee = (fundraiser.contributor_count * Config.SERVICE_FEE_PER_ENTRY) + Config.REPORT_FEE

    result = initiate_stk_push(
        phone=phone,
        amount=total_fee,
        account_reference=fundraiser.code,
        description=f"M-Changia fee",
        fundraiser_id=fundraiser.id
    )

    if result.get('success'):
        _sms(phone,
             f"📱 *M-Pesa request sent!*\n\n"
             f"Amount: KES {total_fee:,.0f}\n"
             f"Check your phone and enter your M-Pesa PIN.\n\n"
             f"Your PDF Audit Report will be sent here automatically after payment confirms.")
    else:
        shortcode = Config.DARAJA_SHORTCODE
        _sms(phone,
             f"❌ Could not send M-Pesa request automatically.\n\n"
             f"Please pay manually:\n"
             f"Paybill: *{shortcode}*\n"
             f"Account: *{fundraiser.code}*\n"
             f"Amount: KES {total_fee:,.0f}\n\n"
             f"Then type *paid* once done.")
    return 'stk_sent'


# ──────────────────────────────────────────────────────────────
# M-PESA CALLBACK (from app.py)
# ──────────────────────────────────────────────────────────────

def handle_mpesa_callback(data: dict) -> str:
    """
    Processes the Daraja STK Push callback.
    Called by app.py when Safaricom hits /webhook/mpesa.
    On success: closes fundraiser + sends PDF confirmation.
    On failure: notifies treasurer and resets to 'closing' state.
    """
    try:
        stk = data.get('Body', {}).get('stkCallback', {})
        result_code = stk.get('ResultCode')
        checkout_id = stk.get('CheckoutRequestID')

        txn = MpesaTransaction.query.filter_by(
            checkout_request_id=checkout_id
        ).first()

        if not txn:
            logger.warning(f"⚠️ No transaction for CheckoutRequestID: {checkout_id}")
            return 'transaction_not_found'

        fundraiser = Fundraiser.query.get(txn.fundraiser_id)

        if result_code == 0:
            # ── Payment successful ───────────────────────────
            items = stk.get('CallbackMetadata', {}).get('Item', [])
            receipt = next(
                (i['Value'] for i in items if i.get('Name') == 'MpesaReceiptNumber'),
                'N/A'
            )

            txn.status = 'success'
            txn.mpesa_receipt = receipt
            txn.updated_at = datetime.utcnow()

            if fundraiser:
                fundraiser.status = 'closed'
                fundraiser.closed_at = datetime.utcnow()

                session = Session.query.filter_by(fundraiser_id=fundraiser.id).first()
                if session:
                    session.state = 'idle'
                    session.fundraiser_id = None

            db.session.commit()

            # Generate PDF
            pdf_path = generate_fundraiser_report(fundraiser)
            pdf_note = (
                "📄 Your PDF Audit Report has been generated! "
                "_(PDF delivery via WhatsApp coming soon — "
                "check your email or request it again)_"
                if pdf_path else
                "⚠️ PDF generation had an issue. Please contact support."
            )

            _sms(txn.phone,
                 f"✅ *Payment Confirmed!*\n"
                 f"Receipt: {receipt}\n\n"
                 f"{pdf_note}\n\n"
                 f"*{fundraiser.name if fundraiser else 'Fundraiser'}* is now closed.\n\n"
                 f"Thank you for using M-Changia! 🙏\n"
                 f"Type *new* to start another fundraiser.")

        else:
            # ── Payment failed / cancelled ────────────────
            txn.status = 'failed'
            txn.updated_at = datetime.utcnow()

            session = Session.query.filter_by(fundraiser_id=txn.fundraiser_id).first()
            if session:
                session.state = 'closing'
            db.session.commit()

            _sms(txn.phone,
                 "❌ *Payment was not completed.*\n\n"
                 "Type *pay* to try again, or *back* to continue the fundraiser.")

        return 'callback_processed'

    except Exception as e:
        logger.error(f"❌ Error in mpesa callback: {str(e)}", exc_info=True)
        return f'error: {str(e)}'


# ──────────────────────────────────────────────────────────────
# INFO MESSAGES
# ──────────────────────────────────────────────────────────────

def _send_status(phone, fundraiser):
    remaining = max(0, fundraiser.target_amount - fundraiser.total_raised)
    _sms(phone,
         f"📊 *{fundraiser.name}*\n"
         f"Code: {fundraiser.code}\n\n"
         f"💰 Raised: KES {fundraiser.total_raised:,.0f}\n"
         f"🎯 Target: KES {fundraiser.target_amount:,.0f}\n"
         f"{fundraiser.progress_bar()} {fundraiser.progress_percentage:.1f}%\n"
         f"👥 Contributors: {fundraiser.contributor_count}\n"
         f"💡 Still need: KES {remaining:,.0f}\n\n"
         f"_Updated: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}_")
    return 'status_sent'


def _send_contributors(phone, fundraiser):
    contributions = Contribution.query.filter_by(
        fundraiser_id=fundraiser.id
    ).order_by(Contribution.logged_at.asc()).all()

    if not contributions:
        _sms(phone, "No contributions logged yet.")
        return 'no_contributions'

    msg = (f"👥 *{fundraiser.name}*\n"
           f"Total: {len(contributions)} contributors | "
           f"KES {fundraiser.total_raised:,.0f}\n"
           f"━━━━━━━━━━━━━━━━\n")

    # Show last 20 to avoid message length limits
    display = contributions[-20:]
    for i, c in enumerate(display, len(contributions) - len(display) + 1):
        msg += f"{i}. {c.contributor_name} — KES {c.amount:,.0f}\n"

    if len(contributions) > 20:
        msg += f"\n_...and {len(contributions) - 20} more. Get PDF report for full list._"

    _sms(phone, msg)
    return 'contributors_sent'


def _send_help(phone):
    _sms(phone,
         "🤖 *M-Changia Commands*\n\n"
         "━━━━━━━━━━━━━━━━\n"
         "*new* — Start a new fundraiser\n"
         "*status* — Current totals & progress\n"
         "*contributors* — List all contributors\n"
         "*close* — End fundraiser & get PDF report\n"
         "*help* — Show this menu\n"
         "━━━━━━━━━━━━━━━━\n"
         "To log a contribution, *forward the M-Pesa "
         "confirmation SMS* directly to this number.\n\n"
         "_M-Changia | Automated Fundraiser Tracking_")
    return 'help_sent'
