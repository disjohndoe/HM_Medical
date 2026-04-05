"""PDF generator for Croatian medical findings (nalazi).

Generates professional A4 documents following Croatian healthcare standards:
- Institution header with contact info and OIB
- Patient data block
- Diagnosis with MKB-10/ICD-10 code
- Clinical content (sadržaj nalaza)
- Recommended therapy table
- Doctor signature area with stamp placeholder
"""

from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Font registration (Croatian diacriticals: šđčćž)
# ---------------------------------------------------------------------------
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "fonts")
_FONT_REGISTERED = False


def _register_fonts() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    regular = os.path.join(_FONTS_DIR, "DejaVuSans.ttf")
    bold = os.path.join(_FONTS_DIR, "DejaVuSans-Bold.ttf")
    if os.path.isfile(regular):
        pdfmetrics.registerFont(TTFont("DejaVuSans", regular))
    if os.path.isfile(bold):
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
    _FONT_REGISTERED = True


# ---------------------------------------------------------------------------
# Record type slug → Croatian label fallback
# ---------------------------------------------------------------------------
_TIP_LABELS: dict[str, str] = {
    "ambulantno_izvjesce": "Ambulantno izvješće",
    "specijalisticki_nalaz": "Specijalistički nalaz",
    "otpusno_pismo": "Otpusno pismo",
    "nalaz": "Nalaz",
    "epikriza": "Epikriza",
    "dijagnoza": "Dijagnoza",
    "misljenje": "Mišljenje",
    "preporuka": "Preporuka",
    "anamneza": "Anamneza",
}

_VRSTA_LABELS: dict[str, str] = {
    "ordinacija": "Ordinacija",
    "poliklinika": "Poliklinika",
    "dom_zdravlja": "Dom zdravlja",
}

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
_COLOR_PRIMARY = colors.HexColor("#1a1a2e")
_COLOR_MUTED = colors.HexColor("#6b7280")
_COLOR_SECTION = colors.HexColor("#374151")
_COLOR_LIGHT_BG = colors.HexColor("#f3f4f6")
_COLOR_BORDER = colors.HexColor("#d1d5db")
_COLOR_MKB_BG = colors.HexColor("#eef2ff")
_COLOR_MKB_TEXT = colors.HexColor("#4338ca")


def _build_styles() -> dict[str, ParagraphStyle]:
    _register_fonts()
    base = getSampleStyleSheet()
    font = "DejaVuSans"
    font_b = "DejaVuSans-Bold"

    return {
        "inst_name": ParagraphStyle(
            "inst_name", parent=base["Normal"],
            fontName=font_b, fontSize=13, leading=16,
            textColor=_COLOR_PRIMARY,
        ),
        "inst_name_center": ParagraphStyle(
            "inst_name_center", parent=base["Normal"],
            fontName=font_b, fontSize=13, leading=16,
            alignment=TA_CENTER, textColor=_COLOR_PRIMARY,
        ),
        "inst_detail": ParagraphStyle(
            "inst_detail", parent=base["Normal"],
            fontName=font, fontSize=8.5, leading=11,
            textColor=_COLOR_MUTED,
        ),
        "doc_type": ParagraphStyle(
            "doc_type", parent=base["Normal"],
            fontName=font_b, fontSize=15, leading=18,
            alignment=TA_CENTER, textColor=_COLOR_PRIMARY,
            spaceAfter=2 * mm,
        ),
        "doc_date": ParagraphStyle(
            "doc_date", parent=base["Normal"],
            fontName=font, fontSize=10, leading=13,
            alignment=TA_CENTER, textColor=_COLOR_MUTED,
        ),
        "section_header": ParagraphStyle(
            "section_header", parent=base["Normal"],
            fontName=font_b, fontSize=10, leading=13,
            textColor=_COLOR_SECTION, spaceBefore=2 * mm, spaceAfter=1.5 * mm,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontName=font, fontSize=10, leading=14,
            textColor=_COLOR_PRIMARY,
        ),
        "body_small": ParagraphStyle(
            "body_small", parent=base["Normal"],
            fontName=font, fontSize=9, leading=12,
            textColor=_COLOR_PRIMARY,
        ),
        "patient_label": ParagraphStyle(
            "patient_label", parent=base["Normal"],
            fontName=font, fontSize=8.5, leading=11,
            textColor=_COLOR_MUTED,
        ),
        "patient_value": ParagraphStyle(
            "patient_value", parent=base["Normal"],
            fontName=font_b, fontSize=9.5, leading=12,
            textColor=_COLOR_PRIMARY,
        ),
        "mkb_badge": ParagraphStyle(
            "mkb_badge", parent=base["Normal"],
            fontName=font_b, fontSize=10, leading=13,
            textColor=_COLOR_MKB_TEXT,
        ),
        "footer_location": ParagraphStyle(
            "footer_location", parent=base["Normal"],
            fontName=font, fontSize=10, leading=13,
            textColor=_COLOR_PRIMARY,
        ),
        "footer_doctor": ParagraphStyle(
            "footer_doctor", parent=base["Normal"],
            fontName=font_b, fontSize=10, leading=13,
            alignment=TA_RIGHT, textColor=_COLOR_PRIMARY,
        ),
        "signed_notice": ParagraphStyle(
            "signed_notice", parent=base["Normal"],
            fontName=font, fontSize=7.5, leading=10,
            alignment=TA_CENTER, textColor=_COLOR_MUTED,
            spaceBefore=3 * mm,
        ),
        "page_num": ParagraphStyle(
            "page_num", parent=base["Normal"],
            fontName=font, fontSize=8, leading=10,
            alignment=TA_RIGHT, textColor=_COLOR_MUTED,
        ),
        "th": ParagraphStyle(
            "th", parent=base["Normal"],
            fontName=font_b, fontSize=8.5, leading=11,
            textColor=_COLOR_SECTION,
        ),
        "td": ParagraphStyle(
            "td", parent=base["Normal"],
            fontName=font, fontSize=9, leading=12,
            textColor=_COLOR_PRIMARY,
        ),
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _format_date_hr(d: date | str | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        parts = d.split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return f"{parts[2]}.{parts[1]}.{parts[0]}."
        return d
    return d.strftime("%d.%m.%Y.")


def _escape(text: str | None) -> str:
    """Escape XML-unsafe characters for reportlab Paragraphs."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _nl2br(text: str | None) -> str:
    """Convert newlines to <br/> for Paragraph, with XML escaping."""
    if not text:
        return ""
    return _escape(text).replace("\n", "<br/>")


def _format_phone(raw: str | None) -> str:
    """Normalize Croatian phone numbers for display on PDF.

    Handles common input formats:
      +38591234567, 0038591234567, 091/234-567, 091 234 567, 01/234-5678
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)

    # International with 00 prefix → +385 …
    if digits.startswith("00385"):
        digits = "385" + digits[5:]
    # International with + (already stripped to digits starting with 385)
    if digits.startswith("385") and len(digits) >= 10:
        rest = digits[3:]  # e.g. "91234567"
        # Croatian mobile prefixes are 2 digits, landline area codes 1-2 digits
        if rest[0] == "1":
            # Zagreb landline: 385 1 XXXXXXX
            return f"+385 1 {_group_digits(rest[1:])}"
        prefix = rest[:2]
        return f"+385 {prefix} {_group_digits(rest[2:])}"

    # Local format starting with 0
    if digits.startswith("0") and len(digits) >= 8:
        if digits.startswith("01"):
            # Zagreb landline: 01 XXXXXXX
            return f"01 {_group_digits(digits[2:])}"
        prefix = digits[:3]  # e.g. 091, 092, 098, 020, 021…
        return f"{prefix} {_group_digits(digits[3:])}"

    # Anything else: return cleaned original (strip extra whitespace)
    return raw.strip()


def _group_digits(s: str) -> str:
    """Group digits into blocks of 3 (last block may be 2-4)."""
    if len(s) <= 4:
        return s
    # Split into chunks of 3, last chunk gets remainder
    chunks = []
    i = 0
    while i < len(s):
        remaining = len(s) - i
        if remaining <= 4:
            chunks.append(s[i:])
            break
        chunks.append(s[i:i + 3])
        i += 3
    return " ".join(chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
class NalazPDFGenerator:
    """Generates an A4 PDF for a Croatian medical finding (nalaz)."""

    def __init__(
        self,
        *,
        tenant: dict,
        doctor: dict,
        patient: dict,
        record: dict,
        record_type_label: str | None = None,
    ):
        self.tenant = tenant or {}
        self.doctor = doctor or {}
        self.patient = patient or {}
        self.record = record or {}
        self.record_type_label = record_type_label or _TIP_LABELS.get(
            self.record.get("tip", ""), self.record.get("tip", "Nalaz")
        )
        self.styles = _build_styles()

    def generate(self) -> bytes:
        """Generate the complete PDF and return raw bytes."""
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=15 * mm,
            title=self.record_type_label,
            author=self.tenant.get("naziv", ""),
        )
        story = self._build_story()
        doc.build(story, onFirstPage=self._draw_page_number, onLaterPages=self._draw_page_number)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Story building (flowable elements)
    # ------------------------------------------------------------------
    def _build_story(self) -> list:
        story: list = []
        story.extend(self._zone_header())
        story.append(Spacer(1, 2 * mm))
        story.extend(self._zone_doc_type())
        story.append(Spacer(1, 3 * mm))
        story.extend(self._zone_patient())
        story.append(Spacer(1, 3 * mm))
        story.extend(self._zone_diagnosis())
        story.append(Spacer(1, 2 * mm))
        story.extend(self._zone_content())
        story.extend(self._zone_therapy())
        # Keep footer together on one page
        footer_block = [Spacer(1, 5 * mm)] + self._zone_footer()
        story.append(KeepTogether(footer_block))
        return story

    # ------------------------------------------------------------------
    # Zone 1: Institution header
    # ------------------------------------------------------------------
    def _zone_header(self) -> list:
        s = self.styles
        t = self.tenant

        naziv = _escape(t.get("naziv", ""))
        vrsta = _VRSTA_LABELS.get(t.get("vrsta", ""), t.get("vrsta", ""))
        adresa = _escape(t.get("adresa", ""))
        grad_line = ""
        if t.get("postanski_broj") or t.get("grad"):
            grad_line = f"{_escape(t.get('postanski_broj', ''))} {_escape(t.get('grad', ''))}".strip()
        telefon = _format_phone(t.get("telefon", ""))
        oib = t.get("oib", "")
        web = t.get("web", "")

        details_lines = []
        if vrsta:
            details_lines.append(_escape(vrsta))
        if adresa:
            details_lines.append(adresa)
        if grad_line:
            details_lines.append(grad_line)
        if telefon:
            details_lines.append(f"Tel: {_escape(telefon)}")
        if oib:
            details_lines.append(f"OIB: {_escape(oib)}")
        if web:
            details_lines.append(_escape(web))

        # Name centered on top, details left-aligned below
        name_para = Paragraph(naziv, s["inst_name_center"])
        details_para = Paragraph("<br/>".join(details_lines), s["inst_detail"])

        header_data = [
            [name_para],
            [details_para],
        ]
        header_table = Table(header_data, colWidths=[180 * mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, _COLOR_BORDER),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 1), (0, 1), 2 * mm),
        ]))
        return [header_table]

    # ------------------------------------------------------------------
    # Zone 2: Document type + date
    # ------------------------------------------------------------------
    def _zone_doc_type(self) -> list:
        s = self.styles
        label = _escape(self.record_type_label).upper()
        datum = _format_date_hr(self.record.get("datum"))
        return [
            Paragraph(label, s["doc_type"]),
            Paragraph(datum, s["doc_date"]),
        ]

    # ------------------------------------------------------------------
    # Zone 3: Patient data block
    # ------------------------------------------------------------------
    def _zone_patient(self) -> list:
        s = self.styles
        p = self.patient

        ime_prezime = f"{_escape(p.get('ime', ''))} {_escape(p.get('prezime', ''))}".strip()
        datum_rodj = _format_date_hr(p.get("datum_rodjenja"))
        spol = "Muški" if p.get("spol") == "M" else "Ženski" if p.get("spol") == "Z" else "—"
        oib = _escape(p.get("oib", "")) or "—"
        mbo = _escape(p.get("mbo", "")) or "—"

        adresa_parts = []
        if p.get("adresa"):
            adresa_parts.append(_escape(p["adresa"]))
        if p.get("postanski_broj") or p.get("grad"):
            adresa_parts.append(f"{_escape(p.get('postanski_broj', ''))} {_escape(p.get('grad', ''))}".strip())
        adresa = ", ".join(adresa_parts) or "—"

        def _cell(label: str, value: str) -> list:
            return [
                Paragraph(label, s["patient_label"]),
                Paragraph(value, s["patient_value"]),
            ]

        data = [
            [
                _cell("Ime i prezime", ime_prezime),
                _cell("OIB", oib),
            ],
            [
                _cell("Datum rođenja", datum_rodj),
                _cell("MBO", mbo),
            ],
            [
                _cell("Spol", spol),
                _cell("Adresa", adresa),
            ],
        ]

        # Flatten cells (each cell is a list of 2 paragraphs stacked)
        flat_data = []
        for row in data:
            flat_row = []
            for cell_parts in row:
                # Stack label + value in one cell
                flat_row.append([cell_parts[0], cell_parts[1]])
            flat_data.append(flat_row)

        table = Table(flat_data, colWidths=[90 * mm, 90 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _COLOR_LIGHT_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, _COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        return [
            Paragraph("PODACI O PACIJENTU", self.styles["section_header"]),
            table,
        ]

    # ------------------------------------------------------------------
    # Zone 4: Diagnosis
    # ------------------------------------------------------------------
    def _zone_diagnosis(self) -> list:
        mkb = self.record.get("dijagnoza_mkb")
        tekst = self.record.get("dijagnoza_tekst")
        if not mkb and not tekst:
            return []

        elements = [Paragraph("DIJAGNOZA", self.styles["section_header"])]

        parts = []
        if mkb:
            parts.append(
                f'<font color="{_COLOR_MKB_TEXT.hexval()}">'
                f"[{_escape(mkb)}]</font>"
            )
        if tekst:
            parts.append(_escape(tekst))

        elements.append(Paragraph("  ".join(parts), self.styles["body"]))
        return elements

    # ------------------------------------------------------------------
    # Zone 5: Content (main body)
    # ------------------------------------------------------------------
    def _zone_content(self) -> list:
        sadrzaj = self.record.get("sadrzaj", "")
        return [
            Paragraph("SADRŽAJ NALAZA", self.styles["section_header"]),
            Paragraph(_nl2br(sadrzaj), self.styles["body"]),
        ]

    # ------------------------------------------------------------------
    # Zone 6: Recommended therapy table
    # ------------------------------------------------------------------
    def _zone_therapy(self) -> list:
        terapija = self.record.get("preporucena_terapija")
        if not terapija:
            return []

        s = self.styles
        elements = [
            Spacer(1, 4 * mm),
            Paragraph("PREPORUČENA TERAPIJA", s["section_header"]),
        ]

        header_row = [
            Paragraph("Naziv", s["th"]),
            Paragraph("Jačina", s["th"]),
            Paragraph("Oblik", s["th"]),
            Paragraph("Doziranje", s["th"]),
            Paragraph("Napomena", s["th"]),
        ]

        data_rows = [header_row]
        for lijek in terapija:
            data_rows.append([
                Paragraph(_escape(lijek.get("naziv", "")), s["td"]),
                Paragraph(_escape(lijek.get("jacina", "")), s["td"]),
                Paragraph(_escape(lijek.get("oblik", "")), s["td"]),
                Paragraph(_escape(lijek.get("doziranje", "")), s["td"]),
                Paragraph(_escape(lijek.get("napomena", "")), s["td"]),
            ])

        col_widths = [50 * mm, 25 * mm, 25 * mm, 35 * mm, 45 * mm]
        table = Table(data_rows, colWidths=col_widths, repeatRows=1)

        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), _COLOR_LIGHT_BG),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, _COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOX", (0, 0), (-1, -1), 0.5, _COLOR_BORDER),
        ]
        # Alternating row backgrounds
        for i in range(1, len(data_rows)):
            if i % 2 == 0:
                style_commands.append(("BACKGROUND", (0, i), (-1, i), _COLOR_LIGHT_BG))

        table.setStyle(TableStyle(style_commands))  # type: ignore[arg-type]
        elements.append(table)
        return elements

    # ------------------------------------------------------------------
    # Zone 7: Footer — doctor signature, stamp, date
    # ------------------------------------------------------------------
    def _zone_footer(self) -> list:
        s = self.styles
        d = self.doctor
        t = self.tenant

        grad = _escape(t.get("grad", ""))
        datum = _format_date_hr(self.record.get("datum"))

        titula = _escape(d.get("titula", "")) or ""
        ime = _escape(d.get("ime", ""))
        prezime = _escape(d.get("prezime", ""))
        doctor_name = f"{titula} {ime} {prezime}".strip()

        location_line = f"{grad}, {datum}" if grad else datum

        footer_left = [
            Paragraph(location_line, s["footer_location"]),
        ]
        footer_right = [
            Spacer(1, 2 * mm),
            Paragraph(doctor_name, s["footer_doctor"]),
        ]

        footer_data = [[footer_left, footer_right]]
        footer_table = Table(footer_data, colWidths=[90 * mm, 90 * mm])
        footer_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        return [
            footer_table,
            Paragraph(
                "Ovaj dokument je digitalno potpisan i kao takav je pravno valjan "
                "bez vlastoručnog potpisa i otiska pečata.",
                s["signed_notice"],
            ),
        ]

    # ------------------------------------------------------------------
    # Page number callback
    # ------------------------------------------------------------------
    @staticmethod
    def _draw_page_number(canvas, doc):
        _register_fonts()
        canvas.saveState()
        canvas.setFont("DejaVuSans", 8)
        canvas.setFillColor(_COLOR_MUTED)
        page_text = f"Stranica {canvas.getPageNumber()}"
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, page_text)
        canvas.restoreState()
