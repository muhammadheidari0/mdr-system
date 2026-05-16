import io
from xml.sax.saxutils import escape as xml_escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from datetime import datetime
from typing import List, Optional

def _build_watermark_drawer(watermark_text: Optional[str]):
    text = (watermark_text or "").strip()
    if not text:
        return None

    def _draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFillColorRGB(0.7, 0.7, 0.7)
        canvas.setFont("Helvetica-Bold", 48)
        canvas.translate(width / 2.0, height / 2.0)
        canvas.rotate(40)
        canvas.drawCentredString(0, 0, text)
        canvas.restoreState()

    return _draw


def generate_transmittal_pdf(transmittal, project_name="MDR Project", watermark_text: Optional[str] = None):
    """
    تولید فایل PDF برای کاور شیت ترنسمیتال
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=1*cm, leftMargin=1*cm, 
        topMargin=1*cm, bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    link_style = ParagraphStyle(
        "DownloadLink",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.blue,
    )
    
    # --- 1. Header Section ---
    # ساختار هدر: لوگو چپ، عنوان وسط، لوگو راست (فرضی)
    header_data = [
        ["Project:", project_name],
        ["Transmittal No:", transmittal.transmittal_no],
        ["Date:", transmittal.created_at.strftime("%Y-%m-%d")],
        ["Subject:", transmittal.subject]
    ]
    
    # استایل هدر
    header_table = Table(header_data, colWidths=[3*cm, 13*cm])
    header_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    
    elements.append(Paragraph("DOCUMENT TRANSMITTAL NOTE", styles['Title']))
    elements.append(Spacer(1, 0.5*cm))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5*cm))

    # --- 2. Sender / Receiver ---
    sr_data = [
        [f"Sender: {transmittal.sender}", f"Receiver: {transmittal.receiver}"]
    ]
    sr_table = Table(sr_data, colWidths=[8*cm, 8*cm])
    sr_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('PADDING', (0,0), (-1,-1), 10),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
    ]))
    elements.append(sr_table)
    elements.append(Spacer(1, 0.5*cm))

    # --- 3. Documents List ---
    # هدر جدول مدارک
    doc_data = [['Row', 'Document Number', 'Rev', 'Status', 'Title', 'Copy', 'Download', 'Remarks']]
    
    # پر کردن جدول با مدارک
    for idx, doc_item in enumerate(transmittal.documents, 1):
        copy_type = []
        selected_kind = str(getattr(doc_item, "file_kind", "pdf") or "pdf").strip().lower()
        file_label = "Native" if selected_kind in {"native", "dwg", "dxf"} else "PDF"
        if doc_item.electronic_copy: copy_type.append(file_label)
        if doc_item.hard_copy: copy_type.append("Hard")
        public_share_url = str(getattr(doc_item, "public_share_url", "") or "").strip()
        download_cell = "-"
        if public_share_url:
            safe_url = xml_escape(public_share_url, {'"': "&quot;"})
            download_cell = Paragraph(f'<link href="{safe_url}"><u>Download</u></link>', link_style)
        
        doc_data.append([
            str(idx),
            doc_item.document_code,
            doc_item.revision,
            doc_item.status,
            doc_item.document_title[:40] + "..." if len(doc_item.document_title or "") > 40 else (doc_item.document_title or ""),
            ", ".join(copy_type),
            download_cell,
            str(getattr(doc_item, "remarks", "") or ""),
        ])

    # تنظیم عرض ستون‌ها
    col_widths = [0.8*cm, 3.9*cm, 1.0*cm, 1.4*cm, 5.6*cm, 1.7*cm, 1.8*cm, 2.6*cm]
    doc_table = Table(doc_data, colWidths=col_widths, repeatRows=1)
    
    doc_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), # Header Font
        ('BACKGROUND', (0,0), (-1,0), colors.navy),    # Header Color
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),    # Header Text
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.whitesmoke]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    elements.append(doc_table)
    elements.append(Spacer(1, 1*cm))

    # --- 4. Notes & Signature ---
    if transmittal.notes:
        elements.append(Paragraph(f"<b>Notes:</b> {transmittal.notes}", styles['Normal']))
        elements.append(Spacer(1, 1*cm))

    # محل امضا
    sig_data = [
        ["Issued By:", "Received By:"],
        ["\n\n_______________________", "\n\n_______________________"],
        ["Date:", "Date:"]
    ]
    sig_table = Table(sig_data, colWidths=[8*cm, 8*cm])
    elements.append(sig_table)

    # ساخت فایل
    watermark_drawer = _build_watermark_drawer(watermark_text)
    if watermark_drawer:
        doc.build(elements, onFirstPage=watermark_drawer, onLaterPages=watermark_drawer)
    else:
        doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_bulk_transmittal_pdf(transmittals: List, project_name="MDR Project"):
    """
    تولید فایل PDF برای چندین ترنسمیتال در یک فایل
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=1*cm, leftMargin=1*cm, 
        topMargin=1*cm, bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    elements.append(Paragraph("BULK TRANSMITTAL REPORT", styles['Title']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Summary Table
    summary_data = [['Transmittal No', 'Date', 'Subject', 'Documents Count']]
    for tr in transmittals:
        summary_data.append([
            tr.transmittal_no,
            tr.created_at.strftime("%Y-%m-%d"),
            tr.subject[:30] + "..." if len(tr.subject or "") > 30 else (tr.subject or ""),
            str(len(tr.documents))
        ])
    
    summary_table = Table(summary_data, colWidths=[4*cm, 2.5*cm, 6*cm, 2*cm])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0,0), (-1,0), colors.navy),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.whitesmoke]),
    ]))
    
    elements.append(summary_table)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
