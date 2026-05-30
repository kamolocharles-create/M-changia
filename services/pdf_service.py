"""
M-Changia PDF Service
Generates a professional audit report PDF for a completed fundraiser.
Uses ReportLab for layout and styling.
"""

import os
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)

logger = logging.getLogger(__name__)

# ── Brand colours ────────────────────────────────────────────
GREEN = colors.HexColor('#1B5E20')
LIGHT_GREEN = colors.HexColor('#E8F5E9')
MID_GREEN = colors.HexColor('#388E3C')
DARK_GRAY = colors.HexColor('#212121')
MID_GRAY = colors.HexColor('#757575')
WHITE = colors.white


def generate_fundraiser_report(fundraiser) -> str:
    """
    Generate a PDF audit report for a completed fundraiser.

    Args:
        fundraiser: Fundraiser model instance

    Returns:
        Absolute path to the generated PDF file,
        or empty string on failure.
    """
    try:
        reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'reports'
        )
        os.makedirs(reports_dir, exist_ok=True)

        filename = f"mchangia_{fundraiser.code}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        filepath = os.path.join(reports_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()

        # ── Custom paragraph styles ──────────────────────────
        title_style = ParagraphStyle(
            'MCTitle', parent=styles['Title'],
            fontSize=22, textColor=GREEN,
            spaceAfter=0.2 * cm, alignment=TA_CENTER,
        )
        subtitle_style = ParagraphStyle(
            'MCSubtitle', parent=styles['Normal'],
            fontSize=11, textColor=MID_GRAY,
            spaceAfter=0.5 * cm, alignment=TA_CENTER,
        )
        section_heading_style = ParagraphStyle(
            'MCSectionHeading', parent=styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold',
            textColor=GREEN, spaceBefore=0.5 * cm, spaceAfter=0.2 * cm,
        )
        footer_style = ParagraphStyle(
            'MCFooter', parent=styles['Normal'],
            fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER,
        )

        story = []

        # ── Header ─────────────────────────────────────────
        story.append(Paragraph("M-Changia", title_style))
        story.append(Paragraph("Official Fundraiser Audit Report", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=2, color=GREEN))
        story.append(Spacer(1, 0.4 * cm))

        # ── Fundraiser Summary ──────────────────────────────
        story.append(Paragraph("FUNDRAISER SUMMARY", section_heading_style))

        closed_date = fundraiser.closed_at or datetime.utcnow()

        summary_data = [
            ["Fundraiser Name", fundraiser.name],
            ["Reference Code", fundraiser.code],
            ["Treasurer Phone", fundraiser.treasurer_phone],
            ["Target Amount", f"KES {fundraiser.target_amount:,.0f}"],
            ["Total Raised", f"KES {fundraiser.total_raised:,.0f}"],
            ["Achievement", f"{fundraiser.progress_percentage:.1f}% of target"],
            ["Total Contributors", str(fundraiser.contributor_count)],
            ["Date Started", fundraiser.created_at.strftime('%d %B %Y')],
            ["Date Closed", closed_date.strftime('%d %B %Y')],
            ["Report Generated", datetime.now().strftime('%d %B %Y at %H:%M')],
        ]

        summary_table = Table(summary_data, colWidths=[5.5 * cm, 11.5 * cm])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), GREEN),
            ('TEXTCOLOR', (1, 0), (1, -1), DARK_GRAY),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, LIGHT_GREEN]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDBDBD')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.6 * cm))

        # ── Contribution Ledger ─────────────────────────────
        story.append(Paragraph(
            f"CONTRIBUTION LEDGER — {fundraiser.contributor_count} Entries",
            section_heading_style
        ))

        header_row = ["#", "Contributor Name", "Phone", "Amount (KES)", "M-Pesa Ref", "Date & Time"]
        ledger_data = [header_row]

        contributions = sorted(fundraiser.contributions, key=lambda c: c.logged_at)
        for i, c in enumerate(contributions, 1):
            ledger_data.append([
                str(i),
                c.contributor_name,
                c.contributor_phone or '-',
                f"{c.amount:,.0f}",
                c.mpesa_ref or '-',
                c.logged_at.strftime('%d/%m/%y %H:%M'),
            ])

        # Totals row
        ledger_data.append(["", "TOTAL", "", f"KES {fundraiser.total_raised:,.2f}", "", ""])

        col_widths = [0.8 * cm, 4.5 * cm, 3.2 * cm, 2.5 * cm, 3 * cm, 3 * cm]
        ledger_table = Table(ledger_data, colWidths=col_widths, repeatRows=1)
        ledger_table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), GREEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [WHITE, LIGHT_GREEN]),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),   # Names left-aligned

            # Totals row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#C8E6C9')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 9),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDBDBD')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(ledger_table)
        story.append(Spacer(1, 0.6 * cm))

        # ── Footer ─────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=MID_GREEN))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"This is an official audit report generated by M-Changia. "
            f"Code: {fundraiser.code} | "
            f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')} | "
            f"Total Verified: KES {fundraiser.total_raised:,.0f}",
            footer_style
        ))

        doc.build(story)
        logger.info(f"✅ PDF report generated: {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"❌ PDF generation failed: {str(e)}", exc_info=True)
        return ''
