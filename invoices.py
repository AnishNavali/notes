"""
invoices.py – GST-compliant invoice PDF generation and email delivery.

Generates a GST Tax Invoice as a PDF (via fpdf2 — pure Python, no system deps)
and emails it to the customer after every successful Razorpay payment.

GST rules applied:
  - CGST (9%) + SGST (9%) when customer state == business state (intrastate)
  - IGST (18%) when customer state != business state (interstate)
  - SAC code 998314 — software subscription services

Environment variables required (see .env):
  BUSINESS_NAME, BUSINESS_GSTIN, BUSINESS_ADDRESS, BUSINESS_STATE
  BUSINESS_EMAIL, BUSINESS_PHONE, BUSINESS_SAC_CODE (default: 998314)
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
"""

import os
import smtplib
import threading
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO

from fpdf import FPDF

import db

# ---------------------------------------------------------------------------
# Business config (your GST details)
# ---------------------------------------------------------------------------

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Your Business Name")
BUSINESS_GSTIN = os.getenv("BUSINESS_GSTIN", "")
BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "")
BUSINESS_STATE = os.getenv("BUSINESS_STATE", "").strip().lower()
BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", "")
BUSINESS_PHONE = os.getenv("BUSINESS_PHONE", "")
BUSINESS_SAC = os.getenv("BUSINESS_SAC_CODE", "998314")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

GST_RATE = 0.18


# ---------------------------------------------------------------------------
# Invoice number generation
# ---------------------------------------------------------------------------


def _next_invoice_number() -> str:
    """
    Sequential invoice number per Indian financial year.
    Format: INV-YYYY-NNNN  e.g. INV-2026-0001. Resets every April 1.
    """
    now = datetime.now(timezone.utc)
    fy_start_year = now.year if now.month >= 4 else now.year - 1
    fy_label = str(fy_start_year)

    counter_doc = db.get_collection("invoice_counters").find_one_and_update(
        {"fy": fy_label},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter_doc["seq"]
    return f"INV-{fy_label}-{seq:04d}"


# ---------------------------------------------------------------------------
# GST calculation
# ---------------------------------------------------------------------------


def _calculate_gst(amount_with_tax: int, customer_state: str) -> dict:
    """
    Back-calculate taxable amount and GST components from a tax-inclusive total.
    """
    total_paise = amount_with_tax
    taxable_paise = round(total_paise / (1 + GST_RATE))
    gst_paise = total_paise - taxable_paise

    is_intrastate = customer_state.strip().lower() == BUSINESS_STATE

    if is_intrastate:
        cgst = round(gst_paise / 2)
        sgst = gst_paise - cgst
        igst = 0
    else:
        cgst = 0
        sgst = 0
        igst = gst_paise

    def fmt(paise: int) -> str:
        return f"Rs.{paise / 100:.2f}"

    return {
        "taxable": taxable_paise,
        "cgst_paise": cgst,
        "sgst_paise": sgst,
        "igst_paise": igst,
        "total_paise": total_paise,
        "taxable_display": fmt(taxable_paise),
        "cgst_display": fmt(cgst),
        "sgst_display": fmt(sgst),
        "igst_display": fmt(igst),
        "total_display": fmt(total_paise),
        "is_intrastate": is_intrastate,
        "cgst_rate": "9%" if is_intrastate else "0%",
        "sgst_rate": "9%" if is_intrastate else "0%",
        "igst_rate": "0%" if is_intrastate else "18%",
    }


# ---------------------------------------------------------------------------
# PDF generation via fpdf2
# ---------------------------------------------------------------------------

# Colours
_BLACK = (30, 30, 30)
_GREY = (100, 100, 100)
_LIGHT = (244, 244, 244)
_WHITE = (255, 255, 255)
_GREEN = (46, 125, 50)
_DARK = (26, 26, 46)
_BORDER = (221, 221, 221)


def _cell(
    pdf: FPDF,
    w,
    h,
    txt,
    border=0,
    ln=0,
    align="L",
    fill=False,
    bold=False,
    size=10,
    colour=None,
):
    """Convenience wrapper around pdf.cell()."""
    pdf.set_font("Helvetica", "B" if bold else "", size)
    if colour:
        pdf.set_text_color(*colour)
    pdf.cell(
        w,
        h,
        str(txt),
        border=border,
        new_x="RIGHT" if ln == 0 else "LMARGIN",
        new_y="TOP" if ln == 0 else "NEXT",
        align=align,
        fill=fill,
    )
    if colour:
        pdf.set_text_color(*_BLACK)


def _generate_pdf(
    invoice_number: str,
    invoice_date: str,
    customer_name: str,
    customer_email: str,
    customer_gstin: str,
    customer_address: str,
    plan: str,
    payment_id: str | None,
    gst: dict,
) -> bytes:
    """Build the invoice PDF and return raw bytes."""

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Header ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*_DARK)
    # multi_cell wraps long business names across two lines automatically
    pdf.cell(110, 10, BUSINESS_NAME, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GREY)
    for line in [
        BUSINESS_ADDRESS,
        f"GSTIN: {BUSINESS_GSTIN}",
        f"Email: {BUSINESS_EMAIL}  |  Phone: {BUSINESS_PHONE}",
    ]:
        # multi_cell wraps long address lines cleanly
        pdf.multi_cell(100, 5, line, new_x="LMARGIN", new_y="NEXT")

    # "TAX INVOICE" badge — right aligned
    pdf.set_xy(130, 15)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_DARK)
    pdf.cell(65, 10, "TAX INVOICE", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(130, 27)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GREY)
    pdf.cell(
        65, 5, f"Invoice No: {invoice_number}", align="R", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.set_x(130)
    pdf.cell(65, 5, f"Date: {invoice_date}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.cell(
        65,
        5,
        f"Payment ID: {payment_id or 'N/A'}",
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # PAID badge
    pdf.set_xy(155, 47)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_text_color(*_GREEN)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(25, 6, "  PAID  ", align="C", fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(*_BLACK)
    pdf.ln(4)

    # ── Divider ─────────────────────────────────────────────────────────────
    pdf.set_draw_color(*_BORDER)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(5)

    # ── Bill To / Service Details ────────────────────────────────────────────
    y_section = pdf.get_y()

    pdf.set_xy(15, y_section)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_GREY)
    pdf.cell(85, 5, "BILL TO", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_BLACK)
    pdf.cell(85, 6, customer_name, new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GREY)
    pdf.cell(85, 5, customer_email, new_x="LMARGIN", new_y="NEXT")

    if customer_address:
        pdf.set_x(15)
        pdf.cell(85, 5, customer_address, new_x="LMARGIN", new_y="NEXT")

    if customer_gstin:
        pdf.set_x(15)
        pdf.cell(85, 5, f"GSTIN: {customer_gstin}", new_x="LMARGIN", new_y="NEXT")

    # Service details — right column
    pdf.set_xy(110, y_section)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_GREY)
    pdf.cell(85, 5, "SERVICE DETAILS", align="R", new_x="LMARGIN", new_y="NEXT")

    for label, value in [
        ("SAC Code", BUSINESS_SAC),
        ("Service", "Software Subscription"),
        ("Plan", plan.title()),
    ]:
        pdf.set_xy(110, pdf.get_y())
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_GREY)
        pdf.cell(85, 5, f"{label}: {value}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(*_BLACK)
    pdf.ln(8)

    # ── Line items table ─────────────────────────────────────────────────────
    col_w = [10, 105, 25, 40]  # #, Description, SAC, Amount
    headers = ["#", "Description", "SAC", "Amount"]

    pdf.set_fill_color(*_LIGHT)
    pdf.set_draw_color(*_BORDER)
    pdf.set_font("Helvetica", "B", 9)
    for i, (h, w) in enumerate(zip(headers, col_w)):
        align = "R" if i == 3 else "L"
        pdf.cell(w, 8, h, border=1, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    desc = f"Another-AI App - {plan.title()} Plan (Monthly Subscription)"
    row = ["1", desc, BUSINESS_SAC, gst["taxable_display"]]
    for i, (val, w) in enumerate(zip(row, col_w)):
        align = "R" if i == 3 else "L"
        pdf.cell(w, 8, val, border=1, align=align)
    pdf.ln(12)

    # ── Tax summary table ────────────────────────────────────────────────────
    summary_x = 120
    summary_w = [55, 25]

    def summary_row(label, value, bold=False, dark_bg=False):
        pdf.set_x(summary_x)
        if dark_bg:
            pdf.set_fill_color(*_DARK)
            pdf.set_text_color(*_WHITE)
        elif bold:
            pdf.set_fill_color(*_LIGHT)
            pdf.set_text_color(*_BLACK)
        else:
            pdf.set_fill_color(*_WHITE)
            pdf.set_text_color(*_BLACK)
        pdf.set_font("Helvetica", "B" if bold or dark_bg else "", 9)
        pdf.cell(summary_w[0], 7, label, border=1, fill=bold or dark_bg, align="L")
        pdf.cell(summary_w[1], 7, value, border=1, fill=bold or dark_bg, align="R")
        pdf.ln()

    summary_row("Taxable Amount", gst["taxable_display"])
    if gst["is_intrastate"]:
        summary_row(f"CGST @ {gst['cgst_rate']}", gst["cgst_display"])
        summary_row(f"SGST @ {gst['sgst_rate']}", gst["sgst_display"])
    else:
        summary_row(f"IGST @ {gst['igst_rate']}", gst["igst_display"])
    summary_row("Total", gst["total_display"], dark_bg=True)

    pdf.set_text_color(*_BLACK)

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.ln(10)
    pdf.set_draw_color(*_BORDER)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_GREY)
    pdf.cell(
        0,
        5,
        "This is a computer-generated invoice. No signature required.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0, 5, f"For queries, contact {BUSINESS_EMAIL}", new_x="LMARGIN", new_y="NEXT"
    )

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def _send_invoice_email(
    to_email: str,
    customer_name: str,
    invoice_number: str,
    plan: str,
    pdf_bytes: bytes,
):
    """Send the invoice PDF as an email attachment via SMTP."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[invoices] SMTP not configured — skipping email for {invoice_number}")
        return

    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = f"Invoice {invoice_number} — {BUSINESS_NAME} {plan.title()} Plan"

    body = (
        f"Hi {customer_name},\n\n"
        f"Thank you for your payment. Please find your GST invoice attached.\n\n"
        f"Invoice Number : {invoice_number}\n"
        f"Plan           : {plan.title()}\n\n"
        f"If you have any questions, reply to this email or contact {BUSINESS_EMAIL}.\n\n"
        f"Regards,\n{BUSINESS_NAME}"
    )
    msg.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"{invoice_number}.pdf",
    )
    msg.attach(attachment)

    try:
        if SMTP_PORT == 465:
            # SSL — connect encrypted from the start
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, to_email, msg.as_string())
        else:
            # STARTTLS (port 587 default)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, to_email, msg.as_string())
        print(f"[invoices] Sent {invoice_number} to {to_email}")
    except Exception as e:
        print(f"[invoices] Failed to send {invoice_number} to {to_email}: {e}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_and_send_invoice(
    email: str,
    payment_id: str | None,
    amount_paise: int,
    plan: str,
    currency: str = "INR",
) -> str:
    """
    Generate a GST-compliant invoice PDF and email it to the user.
    Returns the invoice_number so it can be stored in the payments collection.
    Runs in a background thread — never blocks the webhook response.
    """
    invoice_number = _next_invoice_number()

    def _run():
        try:
            user = db.get_one(collection="users", key={"email": email}) or {}
            customer_name = user.get("name") or email
            customer_gstin = user.get("gstin", "")
            customer_address = user.get("billing_address", "")
            customer_state = user.get("state", "")

            invoice_date = datetime.now(timezone.utc).strftime("%d %b %Y")
            gst = _calculate_gst(amount_paise, customer_state)

            pdf_bytes = _generate_pdf(
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                customer_name=customer_name,
                customer_email=email,
                customer_gstin=customer_gstin,
                customer_address=customer_address,
                plan=plan,
                payment_id=payment_id,
                gst=gst,
            )

            _send_invoice_email(
                to_email=email,
                customer_name=customer_name,
                invoice_number=invoice_number,
                plan=plan,
                pdf_bytes=pdf_bytes,
            )
        except Exception as e:
            print(f"[invoices] Error generating invoice {invoice_number}: {e}")

    # daemon=False — thread completes even if main process is winding down
    threading.Thread(target=_run, daemon=False).start()
    return invoice_number
