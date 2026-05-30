"""
M-Changia SMS Parser
Parses M-Pesa confirmation SMS messages to extract:
  - Sender name
  - Amount
  - Phone number
  - Transaction reference

Handles the 4 most common M-Pesa received-money SMS formats.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedSMS:
    amount: float
    sender_name: str
    sender_phone: str
    mpesa_ref: str
    is_valid: bool
    raw_text: str


def parse_mpesa_sms(text: str) -> Optional[ParsedSMS]:
    """
    Parses a forwarded M-Pesa confirmation SMS.
    Returns ParsedSMS if it's a valid received-money message, None otherwise.

    Sample M-Pesa SMS formats this handles:
    ──────────────────────────────────────────────────────────
    1. "MPesa Confirmed.You have received Ksh1,500.00 from
       JOHN KAMAU 0722123456 on 28/5/26 at 10:30 AM.
       New M-Pesa balance is Ksh5,000.00. Transaction cost, Ksh0.00.
       Transaction ID: QAB1234567"

    2. "Confirmed. Ksh1,500.00 received from JOHN KAMAU
       0722123456 on 28/5/26 at 10:30AM. New balance Ksh5,000."

    3. "M-PESA Confirmed. Ksh 1,500.00 received from
       JOHN KAMAU on 28/5/26 at 10:30AM"

    4. "[Fwd: MPesa]You have received KES1500 from
       JOHN KAMAU 0722123456..."
    ──────────────────────────────────────────────────────────
    """

    if not text or len(text.strip()) < 20:
        return None

    text = text.strip()
    text_lower = text.lower()

    # ── Step 1: Quick keyword check ─────────────────────
    mpesa_keywords = ['mpesa', 'm-pesa', 'confirmed', 'received', 'ksh', 'kes']
    if not any(kw in text_lower for kw in mpesa_keywords):
        return None

    # Must be an incoming (received) message, not outgoing
    if 'received' not in text_lower and 'you have received' not in text_lower:
        # Likely an outgoing/sent SMS — ignore
        if any(w in text_lower for w in ['sent to', 'you sent', 'transferred to']):
            return None

    # ── Step 2: Extract amount ───────────────────────────
    amount = None

    # Try various amount patterns
    amount_patterns = [
        r'(?:received\s+)?(?:Ksh|KES|Kes)\s*([\d,]+\.?\d*)',
        r'(?:Ksh|KES|Kes)\s*([\d,]+\.?\d*)\s+received',
    ]
    for pattern in amount_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                amount = float(m.group(1).replace(',', ''))
                if amount > 0:
                    break
            except ValueError:
                continue

    if amount is None or amount <= 0:
        logger.debug(f"Could not parse amount from: {text[:60]}")
        return None

    # ── Step 3: Extract sender name ──────────────────────
    sender_name = None

    name_patterns = [
        # "from JOHN KAMAU 0722..." or "from JOHN KAMAU on..."
        r'from\s+([A-Z][A-Z\s]{3,39}?)\s+(?:07\d{8}|01\d{8}|\+?254\d{9}|on\s)',
        # "from JOHN KAMAU " at end of line
        r'from\s+([A-Z][A-Z\s]{3,39}?)\s*(?:\.|$|\n)',
        # Fallback: any ALL-CAPS name after "from"
        r'from\s+([A-Z][A-Z\s]{3,39})',
    ]
    for pattern in name_patterns:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1).strip()
            # Filter out words that aren't names
            if candidate.upper() not in ('ON', 'AT', 'THE', 'A', 'AN'):
                sender_name = candidate.title()
                break

    if sender_name is None:
        logger.debug(f"Could not parse sender name from: {text[:60]}")
        return None

    # ── Step 4: Extract phone number ─────────────────────
    phone_match = re.search(r'(07\d{8}|01\d{8}|\+?254\d{9})', text)
    sender_phone = phone_match.group(1) if phone_match else 'N/A'

    # ── Step 5: Extract M-Pesa reference code ────────────
    # M-Pesa refs are alphanumeric, 10 characters (e.g., QAB1234567)
    ref_match = re.search(r'\b([A-Z]{2,3}[A-Z0-9]{7,9})\b', text)
    mpesa_ref = ref_match.group(1) if ref_match else 'N/A'

    logger.info(f"✅ Parsed SMS: KES {amount} from {sender_name} ({sender_phone}) Ref: {mpesa_ref}")

    return ParsedSMS(
        amount=amount,
        sender_name=sender_name,
        sender_phone=sender_phone,
        mpesa_ref=mpesa_ref,
        is_valid=True,
        raw_text=text,
    )
