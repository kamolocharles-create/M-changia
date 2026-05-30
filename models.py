"""
M-Changia Database Models
SQLAlchemy ORM definitions for all tables
"""

import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Fundraiser(db.Model):
    """One harambee / michango event"""
    __tablename__ = 'fundraisers'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)        # e.g., MCH-A3F7
    name = db.Column(db.String(200), nullable=False)                     # Funeral for Mama Wanjiku
    target_amount = db.Column(db.Float, nullable=False)
    treasurer_phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='active')                  # active | closing | closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    contributions = db.relationship('Contribution', backref='fundraiser', lazy=True)

    # ── Computed properties ────────────────────────────

    @property
    def total_raised(self):
        return sum(c.amount for c in self.contributions)

    @property
    def contributor_count(self):
        return len(self.contributions)

    @property
    def progress_percentage(self):
        if self.target_amount == 0:
            return 0.0
        return min((self.total_raised / self.target_amount) * 100, 100.0)

    def progress_bar(self, width=15):
        """Returns a Unicode progress bar, e.g. ▓▓▓▓▓░░░░░ 33%"""
        filled = int((self.progress_percentage / 100) * width)
        empty = width - filled
        return '▓' * filled + '░' * empty

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'target_amount': self.target_amount,
            'total_raised': self.total_raised,
            'contributor_count': self.contributor_count,
            'progress_percentage': round(self.progress_percentage, 1),
            'status': self.status,
        }


class Contribution(db.Model):
    """One M-Pesa contribution logged to a fundraiser"""
    __tablename__ = 'contributions'

    id = db.Column(db.Integer, primary_key=True)
    fundraiser_id = db.Column(db.Integer, db.ForeignKey('fundraisers.id'), nullable=False)
    contributor_name = db.Column(db.String(100), nullable=False)
    contributor_phone = db.Column(db.String(20), default='N/A')
    amount = db.Column(db.Float, nullable=False)
    mpesa_ref = db.Column(db.String(20), default='N/A')
    raw_sms = db.Column(db.Text)                                         # Original forwarded SMS text
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'contributor_name': self.contributor_name,
            'contributor_phone': self.contributor_phone,
            'amount': self.amount,
            'mpesa_ref': self.mpesa_ref,
            'logged_at': self.logged_at.strftime('%d/%m/%Y %H:%M'),
        }


class Session(db.Model):
    """
    Conversation state for each treasurer's WhatsApp number.
    Tracks where they are in the bot flow.
    """
    __tablename__ = 'sessions'

    phone = db.Column(db.String(20), primary_key=True)
    state = db.Column(db.String(50), default='idle')
    # States: idle | setup_name | setup_target | active | closing

    fundraiser_id = db.Column(db.Integer, db.ForeignKey('fundraisers.id'), nullable=True)
    temp_data = db.Column(db.Text, default='{}')                         # JSON temp storage
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_temp(self):
        try:
            return json.loads(self.temp_data or '{}')
        except Exception:
            return {}

    def set_temp(self, data: dict):
        self.temp_data = json.dumps(data)


class MpesaTransaction(db.Model):
    """Tracks STK Push payment requests for service fees"""
    __tablename__ = 'mpesa_transactions'

    id = db.Column(db.Integer, primary_key=True)
    checkout_request_id = db.Column(db.String(100), unique=True)
    fundraiser_id = db.Column(db.Integer, db.ForeignKey('fundraisers.id'), nullable=True)
    phone = db.Column(db.String(20))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')                 # pending | success | failed
    mpesa_receipt = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
