"""
report_generator.py — Generates OFA-branded DOCX bylaw reports.

Supports three scopes:
  - Provincial: Province-wide overview with county-level aggregations
  - County: Full detail for all municipalities in one county/region
  - Municipality: Deep dive on a single municipality

Layout design:
  - Compact structured comparison tables hold short scannable fields
    (exemption status, bylaw names with clickable PDF links, dates, Yes/No flags).
  - Full-width "Full Bylaw Wordings & Notes" blocks beneath each category print
    100% of tracked verbatim clauses, definitions, limits, expiry notes, and
    additional notes with zero truncation and automatic deduplication.
"""

import io
import os
import re
import datetime
import pandas as pd

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.opc.constants import RELATIONSHIP_TYPE

from db_utils import get_connection, get_report_data, resolve_yes_no, resolve_welfare_codes

# ── Paths ──
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(HERE, "OFA_logo.png")

# ── Official OFA Brand Identity Guidelines (2025–26) ──
FONT_NAME = "Arial"
OFA_RED = RGBColor(0xDC, 0x49, 0x49)          # Valencia (#DC4949)
OFA_CRIMSON = RGBColor(0xD7, 0x18, 0x2A)      # Crimson (#D7182A)
OFA_BLUEWOOD = RGBColor(0x33, 0x4B, 0x58)     # Pickled Bluewood (#334B58)
OFA_LINK_BLUE = RGBColor(0x1F, 0x4E, 0x79)    # Accessible document link blue
DARK_TEXT = RGBColor(0x22, 0x22, 0x22)
MUTED_TEXT = RGBColor(0x5A, 0x64, 0x6B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

HEADER_BG = "334B58"          # Pickled Bluewood table headers
VALENCIA_HEX = "DC4949"       # Valencia accent borders
CHAMPAGNE_BG = "EDE6DE"       # Champagne card header fill
WARM_TINT_BG = "F7F4F0"       # Soft alternating row tint
BORDER_GRAY = "D6D1CB"        # Subtle table & callout border

GREEN_BG = "D4EDDA"
RED_BG = "F8D7DA"
AMBER_BG = "FFF3CD"

PAGE_WIDTH_IN = 7.0           # 8.5" page with 0.75" left/right margins

CATEGORY_ORDER = ["DC", "STORMWATER", "SITE_ALT", "LGD", "TREES", "CHICKENS", "FENCES", "BLDG_FEES"]

CATEGORY_NAMES = {
    "DC": "Development Charges",
    "STORMWATER": "Stormwater",
    "SITE_ALT": "Site Alteration & Fill",
    "LGD": "Livestock Guardian Dogs",
    "TREES": "Tree / Forest Conservation",
    "CHICKENS": "Backyard Chickens",
    "FENCES": "Fence Bylaws",
    "BLDG_FEES": "Farm Building Permit Fees",
}

# Structured, short scannable fields rendered in the category comparison table.
# Each tuple: (db_column, header_label, col_width_in)
# Note: "Municipality" column is prepended automatically.
SHORT_DETAIL_FIELDS = {
    "DC": [
        ("has_dc", "Has DC", 0.75),
        ("fees_bylaw_name", "Fees Bylaw", 2.15),
        ("fees_enacted", "Fees Enacted", 1.05),
        ("fees_expiry", "Fees Expiry", 1.05),
    ],
    "STORMWATER": [
        ("charge_type", "Charge Type", 2.30),
        ("fee_calculation", "Fee Summary", 2.90),
    ],
    "SITE_ALT": [
        ("farm_exemption", "Farm Exempt.", 0.62),
        ("nfp_exemption_scope", "NFP Scope", 1.25),
        ("excess_soil_reg_406_19", "O. Reg. 406/19", 0.68),
        ("fill_captures_ag_materials", "Fill Ag Risk", 0.90),
        ("ag_import_fee_status", "Ag Import Fee", 1.00),
        ("per_m3_rate", "$/m³", 0.58),
        ("est_fee_15000_m3", "15k m³ Est.", 0.72),
    ],
    "LGD": [
        ("has_lgd_definition", "LGD Def.", 0.78),
        ("has_herding_def", "Herding Def.", 0.85),
        ("exempt_license_fees", "Exempt Licence", 0.90),
        ("collar_tag_req", "Collar / Tag", 0.82),
        ("barking_restrictions", "Barking Rules", 0.88),
        ("exempt_barking", "Exempt Barking", 0.92),
    ],
    # TREES has no extra short columns beyond Overview's Exemption status.
    "TREES": [],
    "CHICKENS": [
        ("can_keep", "Can Keep", 0.78),
        ("chicken_limit", "Limit", 1.35),
        ("roosters_allowed", "Roosters", 0.78),
        ("licence_required", "Licence Req.", 0.84),
        ("welfare_requirements", "Welfare Requirements", 1.75),
    ],
    "FENCES": [
        ("has_fence_bylaw", "Has Bylaw", 0.68),
        ("applies_all_lands", "All Lands", 0.68),
        ("replaces_lfa", "Replaces LFA", 0.76),
        ("security_fencing_exemption", "Security Exempt", 0.82),
        ("electrified_fencing_exemption", "Electric Exempt", 0.82),
        ("equal_apportionment", "Equal Apport.", 0.74),
        ("apportionment_bylaw", "Cost-Sharing Bylaw", 1.15),
    ],
    "BLDG_FEES": [
        ("fee_year", "Year", 0.48),
        ("pricing_model", "Pricing Model", 1.32),
        ("rate_per_sqft_livestock", "Barn $/ft²", 0.72),
        ("rate_per_sqft_other_farm", "Shed $/ft²", 0.72),
        ("est_10000_barn", "10k Barn", 0.78),
        ("est_10000_shed", "10k Shed", 0.78),
        ("est_2500_shed", "2.5k Shed", 0.75),
    ],
}

# Long-form wording, definition, limit, and note fields printed in full width
# with zero truncation under "Full Bylaw Wordings & Notes".
# Ordered with most specific detail columns first so deduplication preserves
# the most descriptive label when base `exemption_wording` repeats a detail field.
LONG_WORDING_FIELDS = {
    "DC": [
        ("exemption_wording", "Farm Exemption Wording"),
        ("fees_expiry_notes", "Fees Bylaw Expiry Notes"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "STORMWATER": [
        ("fee_calculation", "Fee Calculation & Schedule"),
        ("exemption_wording", "Exemption / Charge Wording"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "SITE_ALT": [
        ("exception_wording", "Farm Exception Wording"),
        ("guidelines_wording", "Bylaw Purpose & Guidelines"),
        ("exemption_wording", "General Exemption Wording"),
        ("fees_bylaw_name", "Site Alteration Fees / User Fee By-law"),
        ("fee_formula_notes", "Site Alteration Fee Schedule & Rules"),
        ("security_deposit_terms", "Security Deposit & Road Damage Terms"),
        ("peer_review_recovery", "Peer Review & Testing Cost Recovery"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "LGD": [
        ("lgd_definition", "Livestock Guardian Dog Definition"),
        ("herding_definition", "Herding Dog Definition"),
        ("dog_limit", "Dog Limit Provisions"),
        ("exemption_wording", "Additional Exemption / Term Wording"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "TREES": [
        ("bylaw_wording", "Bylaw Scope & Wording"),
        ("farming_exception_wording", "Farming Exception Wording"),
        ("list_of_exceptions", "List of Exceptions"),
        ("exemption_wording", "General Exemption Wording"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "CHICKENS": [
        ("definition", "Poultry / Chicken Definition"),
        ("chicken_limit", "Chicken Limit & Conditions"),
        ("exemption_wording", "Exemption / Definition Wording"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "FENCES": [
        ("fence_notes", "Fence Bylaw Provisions & Notes"),
        ("exemption_wording", "Exemption Wording"),
        ("expiry_notes", "Expiry Notes"),
        ("other_notes", "Additional Notes"),
    ],
    "BLDG_FEES": [
        ("formula_notes", "Verified Fee Schedule & Formula"),
        ("shared_authority", "Building Department / Authority"),
        ("silo_grain_bin_fee", "Silo & Grain Bin Fees"),
        ("manure_storage_fee", "Manure Storage Fees"),
        ("greenhouse_tarp_fee", "Greenhouse / Tarped / Special Structures"),
        ("refundable_deposit", "Deposits & Surcharges"),
        ("other_notes", "Additional Notes"),
    ],
}

# Fields that appear in BOTH the compact table (when short) and full wording block (when long).
INLINE_SUMMARY_THRESHOLD = 85

_INVALID_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_GEMINI_TAG_RE = re.compile(r"^\[GEMINI\s+TIER\s*\d+\s*:\s*([^\]]+)\]\s*", re.IGNORECASE)


# ══════════════════════════════════════════════════════════════
# Text & XML helpers
# ══════════════════════════════════════════════════════════════

def _sanitize_xml(text):
    """Strip XML-illegal control chars and normalize line endings cleanly."""
    if text is None:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = _INVALID_XML_RE.sub("", s)
    return s.strip()


def _is_empty(val):
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    s = _sanitize_xml(val)
    return not s or s.lower() in ("nan", "none")


def _clean(val, max_len=None, single_line=False):
    """Clean a value for display without truncating unless max_len is explicitly passed."""
    if _is_empty(val):
        return "—"
    s = _sanitize_xml(val)
    # Replace internal automated-extraction prefix with clean reader-friendly phrasing
    m = _GEMINI_TAG_RE.match(s)
    if m:
        term = m.group(1).strip()
        rest = s[m.end():].strip()
        s = f'Matched term ("{term}"): {rest}' if rest else f'Matched term: "{term}"'
    if single_line:
        s = re.sub(r"\s*\n+\s*", " — ", s)
    if max_len is not None and len(s) > max_len:
        s = s[:max_len - 3].rstrip() + "..."
    return s


def _normalize_for_dedup(text):
    """Normalize text for duplicate detection between base and detail wording fields."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def _valid_url(val):
    if _is_empty(val):
        return None
    u = _sanitize_xml(val).split()[0]
    if u.lower().startswith(("http://", "https://")):
        return u
    return None


def _resolve(val):
    """Resolve integer-coded Yes/No and normalize casing consistently across all categories."""
    if _is_empty(val):
        return "—"
    s = _sanitize_xml(val)
    if s in ("1", "2", "3", "4", "5"):
        res = resolve_yes_no(s)
    else:
        res = resolve_yes_no(s) if s else "—"
    upper = str(res).strip().upper()
    if upper == "YES":
        return "Yes"
    if upper == "PARTIAL":
        return "Partial"
    if upper == "NO":
        return "No"
    if upper == "N/A":
        return "N/A"
    if upper == "NOT KNOWN":
        return "Not Known"
    return str(res).strip() or "—"


def _set_cell_shading(cell, hex_color):
    """Set background color of a table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_margins(cell, top=55, bottom=55, left=85, right=85):
    """Set clean internal cell padding (in dxa; 20 dxa = 1 pt)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_table_borders(table, border_color=BORDER_GRAY):
    """Apply clean, subtle borders to a table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="{HEADER_BG}"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def _set_row_cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def _set_row_header(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))


def _set_paragraph_shading_and_border(paragraph, fill_hex=None, left_border_hex=None, left_sz="18", bottom_border_hex=None):
    """Apply clean shading and/or accent borders to a native Word paragraph."""
    pPr = paragraph._p.get_or_add_pPr()
    if fill_hex:
        pPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill_hex}"/>'))
    if left_border_hex or bottom_border_hex:
        parts = []
        if left_border_hex:
            parts.append(f'<w:left w:val="single" w:sz="{left_sz}" w:space="6" w:color="{left_border_hex}"/>')
        if bottom_border_hex:
            parts.append(f'<w:bottom w:val="single" w:sz="6" w:space="3" w:color="{bottom_border_hex}"/>')
        pPr.append(parse_xml(f'<w:pBdr {nsdecls("w")}>{"".join(parts)}</w:pBdr>'))


def _add_hyperlink(paragraph, url, text, size=Pt(8.5), bold=False, color=OFA_LINK_BLUE):
    """Insert a real clickable Word hyperlink run into a paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), FONT_NAME)
    rFonts.set(qn("w:hAnsi"), FONT_NAME)
    rFonts.set(qn("w:cs"), FONT_NAME)
    rPr.append(rFonts)

    c = OxmlElement("w:color")
    c.set(qn("w:val"), str(color))
    rPr.append(c)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    if bold:
        rPr.append(OxmlElement("w:b"))

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size.pt * 2)))
    rPr.append(sz)
    szCs = OxmlElement("w:szCs")
    szCs.set(qn("w:val"), str(int(size.pt * 2)))
    rPr.append(szCs)

    new_run.append(rPr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = _sanitize_xml(text)
    new_run.append(t)

    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink


def _add_page_number_field(paragraph, size=Pt(8), color=MUTED_TEXT):
    """Insert dynamic 'Page X of Y' Word fields in footer."""
    for label, field_name in (("Page ", "PAGE"), (" of ", "NUMPAGES")):
        r_lbl = paragraph.add_run(label)
        r_lbl.font.name = FONT_NAME
        r_lbl.font.size = size
        r_lbl.font.color.rgb = color

        run = paragraph.add_run()
        run.font.name = FONT_NAME
        run.font.size = size
        run.font.color.rgb = color
        fldChar1 = OxmlElement("w:fldChar")
        fldChar1.set(qn("w:fldCharType"), "begin")
        instrText = OxmlElement("w:instrText")
        instrText.set(qn("xml:space"), "preserve")
        instrText.text = f" {field_name} "
        fldChar2 = OxmlElement("w:fldChar")
        fldChar2.set(qn("w:fldCharType"), "separate")
        fldChar3 = OxmlElement("w:fldChar")
        fldChar3.set(qn("w:fldCharType"), "end")
        run._r.append(fldChar1)
        run._r.append(instrText)
        run._r.append(fldChar2)
        run._r.append(fldChar3)


def _status_bg(status):
    """Return background hex for an exemption status string."""
    s = str(status).strip().upper()
    if s == "YES":
        return GREEN_BG
    if s == "NO":
        return RED_BG
    if s in ("PARTIAL", "N/A", "NOT KNOWN", "NO EXPLICIT EXEMPTION FOUND"):
        return AMBER_BG
    return None


def _set_cell(cell, value, bold=False, size=Pt(8.5), color=DARK_TEXT, align=None):
    """Set cell text (or clickable link / list of link tuples) with uniform Arial styling."""
    cell.text = ""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    if align is not None:
        p.alignment = align

    def _render_item(target_p, item):
        if isinstance(item, dict) and item.get("url"):
            _add_hyperlink(target_p, item["url"], item.get("text") or "View Bylaw", size=size, bold=bold)
        else:
            txt = item.get("text", "") if isinstance(item, dict) else str(item)
            run = target_p.add_run(txt)
            run.font.size = size
            run.font.name = FONT_NAME
            if bold:
                run.bold = True
            if color:
                run.font.color.rgb = color

    if isinstance(value, list):
        for idx, item in enumerate(value):
            target_p = p if idx == 0 else cell.add_paragraph()
            target_p.paragraph_format.space_before = Pt(1)
            target_p.paragraph_format.space_after = Pt(1)
            if align is not None:
                target_p.alignment = align
            _render_item(target_p, item)
    else:
        _render_item(p, value)


def _set_table_fixed_width(table, widths_in):
    """Lock exact table width and column grid widths (dxa) so edges align crisply to margins."""
    total_dxa = int(round(sum(widths_in) * 1440))
    tblPr = table._tbl.tblPr
    for tag in ("w:tblW", "w:tblLayout"):
        existing = tblPr.find(qn(tag))
        if existing is not None:
            tblPr.remove(existing)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(total_dxa))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblLayout = OxmlElement("w:tblLayout")
    tblLayout.set(qn("w:type"), "fixed")
    tblPr.append(tblLayout)

    tblGrid = table._tbl.tblGrid
    if tblGrid is not None:
        for child in list(tblGrid):
            tblGrid.remove(child)
        for w in widths_in:
            gridCol = OxmlElement("w:gridCol")
            gridCol.set(qn("w:w"), str(int(round(w * 1440))))
            tblGrid.append(gridCol)


def _set_cell_width_dxa(cell, width_in):
    dxa = int(round(width_in * 1440))
    tcPr = cell._tc.get_or_add_tcPr()
    existing = tcPr.find(qn("w:tcW"))
    if existing is not None:
        tcPr.remove(existing)
    tcW = OxmlElement("w:tcW")
    tcW.set(qn("w:w"), str(dxa))
    tcW.set(qn("w:type"), "dxa")
    tcPr.append(tcW)


def _add_table(doc, headers, rows, col_widths=None, center_cols=None, keep_header_with_first_row=False):
    """Create an OFA-branded styled table with repeating headers, cantSplit rows, and zero truncation."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_borders(table)

    # Normalize column widths to exact PAGE_WIDTH_IN
    if col_widths and len(col_widths) == len(headers):
        total_w = sum(col_widths)
        widths = [w * (PAGE_WIDTH_IN / total_w) for w in col_widths]
    else:
        widths = [PAGE_WIDTH_IN / len(headers)] * len(headers)

    _set_table_fixed_width(table, widths)
    center_set = set(center_cols or [])

    # Header row
    hdr_row = table.rows[0]
    _set_row_header(hdr_row)
    _set_row_cant_split(hdr_row)
    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        _set_cell_width_dxa(cell, widths[i])
        _set_cell_margins(cell, top=65, bottom=65, left=75, right=75)
        align = WD_ALIGN_PARAGRAPH.CENTER if i in center_set else WD_ALIGN_PARAGRAPH.LEFT
        _set_cell(cell, h, bold=True, size=Pt(8.5), color=WHITE, align=align)
        if keep_header_with_first_row:
            cell.paragraphs[0].paragraph_format.keep_with_next = True
        _set_cell_shading(cell, HEADER_BG)

    # Data rows
    for r_idx, row_data in enumerate(rows):
        row = table.add_row()
        _set_row_cant_split(row)
        for c_idx, val in enumerate(row_data):
            cell = row.cells[c_idx]
            _set_cell_width_dxa(cell, widths[c_idx])
            _set_cell_margins(cell, top=50, bottom=50, left=75, right=75)
            align = WD_ALIGN_PARAGRAPH.CENTER if c_idx in center_set else WD_ALIGN_PARAGRAPH.LEFT
            if isinstance(val, (dict, list)):
                rendered = val
            else:
                rendered = _clean(val)
            _set_cell(cell, rendered, size=Pt(8.5), color=DARK_TEXT, align=align)
        if r_idx % 2 == 1:
            for cell in row.cells:
                _set_cell_shading(cell, WARM_TINT_BG)

    return table


def _heading(doc, text, level=1):
    """Add an OFA-branded heading with uniform Arial typography."""
    h = doc.add_heading(text, level=level)
    h.paragraph_format.keep_with_next = True
    color = OFA_RED if level == 1 else OFA_BLUEWOOD
    size = Pt(16) if level == 1 else Pt(12.5) if level == 2 else Pt(10.5)
    for run in h.runs:
        run.font.name = FONT_NAME
        run.font.color.rgb = color
        run.font.size = size
        run.bold = True
    if level == 1:
        _set_paragraph_shading_and_border(h, bottom_border_hex=VALENCIA_HEX)
    return h


def _body_para(doc, text, space_after=Pt(6), size=Pt(10), italic=False, color=DARK_TEXT):
    """Add a standard body paragraph locked to uniform Arial."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = space_after
    run = p.add_run(_sanitize_xml(text))
    run.font.name = FONT_NAME
    run.font.size = size
    run.italic = italic
    run.font.color.rgb = color
    return p


def _configure_page_and_footer(doc):
    """Configure margins and OFA Brand Guide contact footer on content pages."""
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11.0)
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    section.different_first_page_header_footer = True

    footer = section.footer
    p = footer.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(0)
    pPr = p._p.get_or_add_pPr()
    pPr.append(
        parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            f'  <w:top w:val="single" w:sz="4" w:space="4" w:color="{VALENCIA_HEX}"/>'
            f'</w:pBdr>'
        )
    )
    # Right-aligned tab stop at 7.0" for page numbers
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:pos"), str(int(PAGE_WIDTH_IN * 1440)))
    tabs.append(tab)
    pPr.append(tabs)

    r1 = p.add_run("Ontario Federation of Agriculture   |   ofa.on.ca  //  Tel: 519-821-8883 / 1-800-668-3276\t")
    r1.font.name = FONT_NAME
    r1.font.size = Pt(8)
    r1.font.color.rgb = MUTED_TEXT
    _add_page_number_field(p, size=Pt(8), color=MUTED_TEXT)


# ══════════════════════════════════════════════════════════════
# Report sections
# ══════════════════════════════════════════════════════════════

def _add_cover_page(doc, scope, scope_value, include_full_wordings=True):
    """OFA-branded cover page following OFA Brand Identity Guidelines."""
    for _ in range(3):
        doc.add_paragraph("")

    if os.path.exists(LOGO_PATH):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(LOGO_PATH, width=Inches(3.0))

    doc.add_paragraph("")

    titles = {
        "provincial": ("Ontario Municipal Bylaw Report", "Province-Wide Overview"),
        "county": (f"{scope_value}\nMunicipal Bylaw Report", "County / Region Overview"),
        "municipality": (f"{scope_value}\nBylaw Report", "Municipality Report"),
    }
    title, subtitle = titles.get(scope, ("Bylaw Report", ""))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(title)
    run.font.size = Pt(26)
    run.font.color.rgb = OFA_RED
    run.bold = True
    run.font.name = FONT_NAME

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(14)
    run = p.add_run(subtitle)
    run.font.size = Pt(15)
    run.font.color.rgb = OFA_BLUEWOOD
    run.bold = True
    run.font.name = FONT_NAME

    if scope != "provincial":
        mode_note = (
            "Complete Edition — Includes Full Verbatim Bylaw Wordings & Notes"
            if include_full_wordings
            else "Summary Edition — Compact Comparison Tables"
        )
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(18)
        run = p.add_run(mode_note)
        run.font.size = Pt(10)
        run.font.color.rgb = MUTED_TEXT
        run.font.name = FONT_NAME

    doc.add_paragraph("")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(f"Generated: {datetime.date.today().strftime('%B %d, %Y')}")
    run.font.size = Pt(11)
    run.font.color.rgb = DARK_TEXT
    run.font.name = FONT_NAME

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(24)
    run = p.add_run("Prepared by the Ontario Federation of Agriculture — Farms and Food Forever")
    run.font.size = Pt(10)
    run.italic = True
    run.font.color.rgb = MUTED_TEXT
    run.font.name = FONT_NAME

    doc.add_page_break()


def _add_executive_summary(doc, data):
    """Exemption scorecard across all 7 categories."""
    munis = data["municipalities"]
    bylaws = data["bylaws"]
    signals = data["signals"]
    scope = data["scope"]

    _heading(doc, "Executive Summary")

    n_munis = len(munis)
    n_signals = len(signals)

    if scope == "provincial":
        n_counties = munis["geographic_area"].nunique()
        _body_para(
            doc,
            f"This report covers {n_munis} municipalities across {n_counties} "
            f"counties and regions in Ontario, with {n_signals} recent intelligence signals.",
        )
    elif scope == "county":
        _body_para(
            doc,
            f"This report covers {n_munis} municipalities in {data['scope_value']}, "
            f"with {n_signals} recent intelligence signals for this area.",
        )
    else:
        _body_para(doc, f"Detailed bylaw analysis for {data['scope_value']}.")

    _heading(doc, "Exemption Scorecard", level=2)
    headers = ["Category", "Yes", "Partial", "No", "N/A", "Unknown", "Total", "Bylaw %", "Full Exempt %"]
    rows = []

    for cat in CATEGORY_ORDER:
        cat_bylaws = bylaws[bylaws["category"] == cat]
        if cat_bylaws.empty:
            rows.append([CATEGORY_NAMES[cat], "0", "0", "0", "0", "0", "0", "—", "—"])
            continue
        statuses = cat_bylaws["exemption_status"].apply(_resolve)
        yes = int((statuses == "Yes").sum())
        partial = int((statuses == "Partial").sum())
        no = int((statuses == "No").sum())
        na = int(statuses.isin(["N/A"]).sum())
        nk = int(len(statuses) - yes - partial - no - na)
        total = int(len(statuses))

        active_bylaws = yes + partial + no
        bylaw_cov = f"{active_bylaws / total * 100:.0f}%" if total > 0 else "—"
        exempt_cov = f"{yes / active_bylaws * 100:.0f}%" if active_bylaws > 0 else "—"

        rows.append([
            CATEGORY_NAMES[cat], str(yes), str(partial), str(no), str(na),
            str(nk), str(total), bylaw_cov, exempt_cov,
        ])

    table = _add_table(
        doc,
        headers,
        rows,
        col_widths=[1.85, 0.50, 0.58, 0.50, 0.50, 0.72, 0.55, 0.85, 0.95],
        center_cols=[1, 2, 3, 4, 5, 6, 7, 8],
    )

    for i, row_data in enumerate(rows):
        cov = row_data[8]
        if cov != "—":
            pct = int(cov.replace("%", ""))
            bg = GREEN_BG if pct >= 70 else AMBER_BG if pct >= 40 else RED_BG
            _set_cell_shading(table.rows[i + 1].cells[8], bg)

    doc.add_page_break()


def _add_category_section(doc, data, cat_code, include_full_wordings=True):
    """One section per bylaw category."""
    scope = data["scope"]
    bylaws = data["bylaws"]
    details_df = data["details"].get(cat_code, pd.DataFrame())
    cat_name = CATEGORY_NAMES[cat_code]
    cat_bylaws = bylaws[bylaws["category"] == cat_code].copy()

    _heading(doc, cat_name)

    if cat_bylaws.empty:
        _body_para(doc, "No data available for this category.")
        doc.add_page_break()
        return

    statuses = cat_bylaws["exemption_status"].apply(_resolve)
    yes = int((statuses == "Yes").sum())
    partial = int((statuses == "Partial").sum())
    no = int((statuses == "No").sum())
    na = int(statuses.isin(["N/A"]).sum())
    total = int(len(statuses))

    active_bylaws = yes + partial + no
    bylaw_cov = f"{active_bylaws / total * 100:.0f}%" if total > 0 else "0%"
    exempt_cov = f"{yes / active_bylaws * 100:.0f}%" if active_bylaws > 0 else "N/A"

    bylaw_word = "active bylaw" if active_bylaws == 1 else "active bylaws"
    partial_clause = (
        f", {partial} {'has' if partial == 1 else 'have'} a partial (statutory-only) exemption"
        if partial > 0
        else ""
    )
    no_verb = "active bylaw has" if no == 1 else "active bylaws have"
    na_word = "municipality does" if na == 1 else "municipalities do"

    _body_para(
        doc,
        f"Bylaw presence: {bylaw_cov} ({active_bylaws} {bylaw_word} identified out of {total} municipalities). "
        f"Full farm exemption coverage: {exempt_cov} ({yes} out of {active_bylaws} {bylaw_word}){partial_clause}; "
        f"{no} {no_verb} no exemption, and {na} {na_word} not have this type of bylaw.",
    )

    if scope == "provincial":
        _add_category_provincial(doc, cat_bylaws)
    else:
        _add_category_detail(doc, cat_code, cat_bylaws, details_df, include_full_wordings=include_full_wordings)

    doc.add_page_break()


def _add_category_provincial(doc, cat_bylaws):
    """County-level aggregation table for provincial reports."""
    _heading(doc, "County / Region Summary", level=2)

    cat_bylaws = cat_bylaws.copy()
    cat_bylaws["_status"] = cat_bylaws["exemption_status"].apply(_resolve)
    has_partial = bool((cat_bylaws["_status"] == "Partial").any())

    if has_partial:
        headers = ["County / Region", "Yes", "Partial", "No", "N/A", "Unknown", "Total", "Bylaw %", "Full Exempt %"]
        widths = [1.85, 0.50, 0.58, 0.50, 0.50, 0.72, 0.55, 0.85, 0.95]
        center_cols = [1, 2, 3, 4, 5, 6, 7, 8]
    else:
        headers = ["County / Region", "Yes", "No", "N/A", "Unknown", "Total", "Bylaw %", "Exempt %"]
        widths = [2.20, 0.58, 0.58, 0.58, 0.78, 0.64, 0.82, 0.82]
        center_cols = [1, 2, 3, 4, 5, 6, 7]

    rows = []

    for county, group in sorted(cat_bylaws.groupby("geographic_area"), key=lambda x: str(x[0])):
        county = county if county and str(county).strip() else "Unassigned"
        s = group["_status"]
        yes = int((s == "Yes").sum())
        partial = int((s == "Partial").sum())
        no = int((s == "No").sum())
        na = int(s.isin(["N/A"]).sum())
        nk = int(len(s) - yes - partial - no - na)
        total = int(len(s))

        active_bylaws = yes + partial + no
        bylaw_cov = f"{active_bylaws / total * 100:.0f}%" if total > 0 else "—"
        exempt_cov = f"{yes / active_bylaws * 100:.0f}%" if active_bylaws > 0 else "—"

        if has_partial:
            rows.append([county, str(yes), str(partial), str(no), str(na), str(nk), str(total), bylaw_cov, exempt_cov])
        else:
            rows.append([county, str(yes), str(no), str(na), str(nk), str(total), bylaw_cov, exempt_cov])

    _add_table(
        doc,
        headers,
        rows,
        col_widths=widths,
        center_cols=center_cols,
    )


def _format_bylaw_cell(row):
    """Build display text / clickable hyperlinks for primary (and optional secondary) bylaw names."""
    items = []
    name1 = _clean(row.get("bylaw_name"), single_line=True)
    link1 = _valid_url(row.get("bylaw_link"))
    if name1 != "—":
        items.append({"text": name1, "url": link1} if link1 else name1)
    elif link1:
        items.append({"text": "View Bylaw Document", "url": link1})

    name2 = _clean(row.get("bylaw_name_2"), single_line=True)
    link2 = _valid_url(row.get("bylaw_link_2"))
    if name2 != "—":
        items.append({"text": name2, "url": link2} if link2 else name2)
    elif link2:
        items.append({"text": "View Secondary Bylaw", "url": link2})

    if not items:
        return "—"
    return items[0] if len(items) == 1 else items


def _add_category_detail(doc, cat_code, cat_bylaws, details_df, include_full_wordings=True):
    """Municipality-level overview table, structured detail table, and full-width wordings block."""
    cat_bylaws = cat_bylaws.sort_values("municipality_name", kind="stable")

    # ── 1. Municipality Overview Table ──
    _heading(doc, "Municipality Overview", level=2)

    headers = ["Municipality", "Exemption", "Bylaw Name", "Enacted", "Expiry"]
    rows = []
    for _, b in cat_bylaws.iterrows():
        status = _resolve(b["exemption_status"])
        rows.append([
            _clean(b.get("municipality_name")),
            status,
            _format_bylaw_cell(b),
            _clean(b.get("date_enacted")),
            _clean(b.get("expiry_date")),
        ])

    table = _add_table(
        doc,
        headers,
        rows,
        col_widths=[1.45, 0.85, 2.90, 0.90, 0.90],
        center_cols=[1, 3, 4],
    )
    for i, row_data in enumerate(rows):
        bg = _status_bg(row_data[1])
        if bg:
            _set_cell_shading(table.rows[i + 1].cells[1], bg)

    # Merge detail columns onto cat_bylaws (left join so base wordings & notes always survive)
    if not details_df.empty:
        merged = cat_bylaws.merge(
            details_df.drop(columns=["id"], errors="ignore"),
            left_on="id",
            right_on="bylaw_id",
            how="left",
            suffixes=("", "_d"),
        )
    else:
        merged = cat_bylaws.copy()

    # ── 2. Structured Comparison Table (Short/Scannable Fields Only) ──
    short_fields = SHORT_DETAIL_FIELDS.get(cat_code, [])
    if short_fields:
        def _has_short_data(r):
            return any(not _is_empty(r.get(f)) for f, _, _ in short_fields)

        short_df = merged[merged.apply(_has_short_data, axis=1)]
        if not short_df.empty:
            doc.add_paragraph("")
            _heading(doc, "Detailed Comparison", level=2)

            muni_w = max(1.25, PAGE_WIDTH_IN - sum(w for _, _, w in short_fields))
            d_headers = ["Municipality"] + [display for _, display, _ in short_fields]
            d_widths = [muni_w] + [w for _, _, w in short_fields]

            # Center short Yes/No/Date columns; keep text columns left-aligned
            left_fields = {
                "fees_bylaw_name",
                "charge_type",
                "fee_calculation",
                "chicken_limit",
                "welfare_requirements",
                "apportionment_bylaw",
                "nfp_exemption_scope",
                "fill_captures_ag_materials",
                "ag_import_fee_status",
                "pricing_model",
                "fee_pricing_model",
            }
            center_cols = [idx + 1 for idx, (f, _, _) in enumerate(short_fields) if f not in left_fields]

            d_rows = []
            for _, row in short_df.iterrows():
                d_row = [_clean(row.get("municipality_name"))]
                for field, _, _ in short_fields:
                    raw_val = row.get(field)
                    if field == "welfare_requirements":
                        val = _clean(resolve_welfare_codes(raw_val)) if not _is_empty(raw_val) else "—"
                    elif field == "fee_year":
                        if _is_empty(raw_val):
                            val = "—"
                        else:
                            try:
                                val = str(int(float(raw_val)))
                            except Exception:
                                val = _clean(raw_val, single_line=True)
                    elif field in ("rate_per_sqft_livestock", "rate_per_sqft_other_farm"):
                        if _is_empty(raw_val):
                            val = "—"
                        else:
                            try:
                                val = f"${float(raw_val):.3f}".rstrip("0")
                                if val.endswith("."):
                                    val += "00"
                                elif len(val.split(".")[1]) == 1:
                                    val += "0"
                            except Exception:
                                val = _clean(raw_val, single_line=True)
                    elif field == "per_m3_rate":
                        if _is_empty(raw_val):
                            val = "—"
                        else:
                            try:
                                val = f"${float(raw_val):,.2f}/m³"
                            except Exception:
                                val = _clean(raw_val, single_line=True)
                    elif field in ("est_2500_shed", "est_10000_barn", "est_10000_shed", "est_20000_barn", "base_fee", "min_fee", "flat_fee", "base_fee_small", "base_fee_large", "est_fee_500_m3", "est_fee_5000_m3", "est_fee_15000_m3"):
                        if _is_empty(raw_val):
                            val = "—"
                        else:
                            try:
                                val = f"${float(raw_val):,.0f}"
                            except Exception:
                                val = _clean(raw_val, single_line=True)
                    elif field == "fees_bylaw_name":
                        fname = _clean(raw_val, single_line=True)
                        flink = _valid_url(row.get("fees_bylaw_link"))
                        if fname != "—":
                            val = {"text": fname, "url": flink} if flink else fname
                        elif flink:
                            val = {"text": "View Fees Bylaw", "url": flink}
                        else:
                            val = "—"
                    elif field in ("chicken_limit", "fee_calculation"):
                        cleaned = _clean(raw_val, single_line=True)
                        if include_full_wordings and cleaned != "—" and len(cleaned) > INLINE_SUMMARY_THRESHOLD:
                            val = "See full wording below"
                        else:
                            val = cleaned
                    else:
                        s_raw = _sanitize_xml(raw_val) if not _is_empty(raw_val) else ""
                        if s_raw in ("1", "2", "3", "4", "5") or s_raw.upper() in ("YES", "PARTIAL", "NO", "N/A", "NOT KNOWN"):
                            val = _resolve(s_raw)
                        else:
                            val = _clean(raw_val, single_line=True)
                    d_row.append(val)
                d_rows.append(d_row)

            _add_table(doc, d_headers, d_rows, col_widths=d_widths, center_cols=center_cols)

    # ── 3. Full-Width Verbatim Bylaw Wordings & Notes (Zero Truncation) ──
    if include_full_wordings:
        _add_category_wordings(doc, cat_code, merged)


def _add_category_wordings(doc, cat_code, merged_df):
    """Render all tracked legal wordings, definitions, limits, and notes at full width with zero truncation."""
    wording_fields = LONG_WORDING_FIELDS.get(cat_code, [])
    if not wording_fields or merged_df.empty:
        return

    # Pre-collect deduplicated wording entries per municipality
    muni_blocks = []
    for _, row in merged_df.iterrows():
        entries = []
        seen_norms = []

        for field, label in wording_fields:
            raw_val = row.get(field)
            if _is_empty(raw_val):
                continue
            text = _clean(raw_val)
            if text == "—":
                continue

            # Skip very short inline fields already shown verbatim in the comparison table
            if field in ("chicken_limit", "fee_calculation") and len(text) <= INLINE_SUMMARY_THRESHOLD:
                # Still register in seen_norms so duplicate exemption_wording doesn't repeat it
                seen_norms.append(_normalize_for_dedup(text))
                continue

            norm = _normalize_for_dedup(text)
            if not norm:
                continue

            # Skip exact or near-exact duplicates already printed under a more specific label
            if any(norm == prev or (len(norm) > 25 and norm in prev) for prev in seen_norms):
                continue

            seen_norms.append(norm)
            entries.append((label, text))

        if entries:
            muni_blocks.append({
                "municipality": _clean(row.get("municipality_name")),
                "status": _resolve(row.get("exemption_status")),
                "bylaw_name": _clean(row.get("bylaw_name"), single_line=True),
                "bylaw_link": _valid_url(row.get("bylaw_link")),
                "bylaw_name_2": _clean(row.get("bylaw_name_2"), single_line=True),
                "bylaw_link_2": _valid_url(row.get("bylaw_link_2")),
                "fees_bylaw_link": _valid_url(row.get("fees_bylaw_link")),
                "entries": entries,
            })

    if not muni_blocks:
        return

    doc.add_paragraph("")
    _heading(doc, "Full Bylaw Wordings & Notes", level=2)
    _body_para(
        doc,
        "Complete untruncated wording, definitions, limits, and notes recorded in the OFA Municipal Bylaw Database.",
        space_after=Pt(8),
        size=Pt(9),
        italic=True,
        color=MUTED_TEXT,
    )

    for block in muni_blocks:
        # Municipality card header bar (shaded Champagne with Valencia left border)
        hdr_p = doc.add_paragraph()
        hdr_p.paragraph_format.space_before = Pt(6)
        hdr_p.paragraph_format.space_after = Pt(4)
        hdr_p.paragraph_format.keep_with_next = True
        _set_paragraph_shading_and_border(hdr_p, fill_hex=CHAMPAGNE_BG, left_border_hex=VALENCIA_HEX, left_sz="24")

        r_muni = hdr_p.add_run(f" {block['municipality']}")
        r_muni.font.name = FONT_NAME
        r_muni.font.size = Pt(10)
        r_muni.bold = True
        r_muni.font.color.rgb = OFA_BLUEWOOD

        r_stat = hdr_p.add_run(f"   |   Exemption: {block['status']}")
        r_stat.font.name = FONT_NAME
        r_stat.font.size = Pt(9)
        r_stat.font.color.rgb = DARK_TEXT

        if block["bylaw_name"] != "—":
            r_sep = hdr_p.add_run("   |   ")
            r_sep.font.name = FONT_NAME
            r_sep.font.size = Pt(9)
            r_sep.font.color.rgb = MUTED_TEXT
            if block["bylaw_link"]:
                _add_hyperlink(hdr_p, block["bylaw_link"], block["bylaw_name"], size=Pt(9))
            else:
                r_bn = hdr_p.add_run(block["bylaw_name"])
                r_bn.font.name = FONT_NAME
                r_bn.font.size = Pt(9)
                r_bn.font.color.rgb = DARK_TEXT
        elif block["bylaw_link"]:
            r_sep = hdr_p.add_run("   |   ")
            r_sep.font.name = FONT_NAME
            r_sep.font.size = Pt(9)
            r_sep.font.color.rgb = MUTED_TEXT
            _add_hyperlink(hdr_p, block["bylaw_link"], "View Bylaw PDF", size=Pt(9))

        if block["bylaw_name_2"] != "—" or block["bylaw_link_2"]:
            r_sep2 = hdr_p.add_run("   |   Secondary: ")
            r_sep2.font.name = FONT_NAME
            r_sep2.font.size = Pt(8.5)
            r_sep2.font.color.rgb = MUTED_TEXT
            sec_label = block["bylaw_name_2"] if block["bylaw_name_2"] != "—" else "View Secondary Bylaw"
            if block["bylaw_link_2"]:
                _add_hyperlink(hdr_p, block["bylaw_link_2"], sec_label, size=Pt(8.5))
            else:
                r_s2 = hdr_p.add_run(sec_label)
                r_s2.font.name = FONT_NAME
                r_s2.font.size = Pt(8.5)
                r_s2.font.color.rgb = DARK_TEXT

        # Full-width wording entries (native paragraphs so long clauses flow naturally across pages)
        for label, text in block["entries"]:
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if not lines:
                continue

            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.14)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.12
            _set_paragraph_shading_and_border(p, left_border_hex=BORDER_GRAY, left_sz="12")

            r_lbl = p.add_run(f"{label}: ")
            r_lbl.font.name = FONT_NAME
            r_lbl.font.size = Pt(9)
            r_lbl.bold = True
            r_lbl.font.color.rgb = OFA_BLUEWOOD

            r_txt = p.add_run(lines[0])
            r_txt.font.name = FONT_NAME
            r_txt.font.size = Pt(9)
            r_txt.font.color.rgb = DARK_TEXT

            # Additional lines within the same field (e.g., numbered subsections)
            for extra_line in lines[1:]:
                p_ext = doc.add_paragraph()
                p_ext.paragraph_format.left_indent = Inches(0.24)
                p_ext.paragraph_format.space_before = Pt(0)
                p_ext.paragraph_format.space_after = Pt(3)
                p_ext.paragraph_format.line_spacing = 1.12
                _set_paragraph_shading_and_border(p_ext, left_border_hex=BORDER_GRAY, left_sz="12")
                r_ext = p_ext.add_run(extra_line)
                r_ext.font.name = FONT_NAME
                r_ext.font.size = Pt(9)
                r_ext.font.color.rgb = DARK_TEXT


def _add_municipality_profiles(doc, data):
    """Individual profiles for each municipality (county scope)."""
    munis = data["municipalities"]
    bylaws = data["bylaws"]
    contacts = data["contacts"]
    signals = data["signals"]

    _heading(doc, "Municipality Profiles")

    for _, muni in munis.iterrows():
        muni_id = muni["id"]
        muni_name = muni["name"]

        _heading(doc, muni_name, level=2)

        # Info line with clickable website
        info_p = doc.add_paragraph()
        info_p.paragraph_format.space_before = Pt(0)
        info_p.paragraph_format.space_after = Pt(3)
        info_p.paragraph_format.keep_with_next = True
        parts = []
        if muni.get("municipal_status"):
            parts.append(f"Status: {muni['municipal_status']}")
        if muni.get("geographic_area"):
            parts.append(f"Region: {muni['geographic_area']}")
        if parts:
            r = info_p.add_run("  |  ".join(parts))
            r.font.name = FONT_NAME
            r.font.size = Pt(9.5)
            r.font.color.rgb = DARK_TEXT
        site_url = _valid_url(muni.get("website"))
        if site_url:
            if parts:
                sep = info_p.add_run("  |  Website: ")
                sep.font.name = FONT_NAME
                sep.font.size = Pt(9.5)
                sep.font.color.rgb = DARK_TEXT
            _add_hyperlink(info_p, site_url, site_url, size=Pt(9.5))
        elif muni.get("website") and not _is_empty(muni.get("website")):
            prefix = "  |  Website: " if parts else "Website: "
            r = info_p.add_run(f"{prefix}{_clean(muni.get('website'))}")
            r.font.name = FONT_NAME
            r.font.size = Pt(9.5)
            r.font.color.rgb = DARK_TEXT

        # Contact info
        contact_parts = []
        muni_contacts = contacts[contacts["municipality_id"] == muni_id]
        if not muni_contacts.empty:
            c = muni_contacts.iloc[0]
            name = f"{c.get('first_name', '') or ''} {c.get('last_name', '') or ''}".strip()
            if name:
                contact_parts.append(f"Contact: {name}")
            if c.get("email"):
                contact_parts.append(f"Email: {c['email']}")
            if c.get("phone"):
                contact_parts.append(f"Phone: {c['phone']}")
        else:
            if muni.get("contact_name"):
                contact_parts.append(f"Contact: {muni['contact_name']}")
            if muni.get("clerk_email"):
                contact_parts.append(f"Email: {muni['clerk_email']}")
            if muni.get("clerk_phone"):
                contact_parts.append(f"Phone: {muni['clerk_phone']}")
        if contact_parts:
            c_p = _body_para(doc, "  |  ".join(contact_parts), space_after=Pt(5), size=Pt(9.5))
            c_p.paragraph_format.keep_with_next = True

        # Bylaw summary table (zero Bylaw Name truncation, clickable PDF links)
        muni_bylaws = bylaws[bylaws["municipality_id"] == muni_id]
        if not muni_bylaws.empty:
            headers = ["Category", "Exemption", "Bylaw", "Expiry"]
            rows = []
            for _, b in muni_bylaws.iterrows():
                status = _resolve(b["exemption_status"])
                rows.append([
                    CATEGORY_NAMES.get(b["category"], b["category"]),
                    status,
                    _format_bylaw_cell(b),
                    _clean(b.get("expiry_date")),
                ])
            table = _add_table(
                doc,
                headers,
                rows,
                col_widths=[1.85, 0.90, 3.30, 0.95],
                center_cols=[1, 3],
                keep_header_with_first_row=True,
            )
            for i, rd in enumerate(rows):
                bg = _status_bg(rd[1])
                if bg:
                    _set_cell_shading(table.rows[i + 1].cells[1], bg)

        # Signals for this muni
        muni_signals = signals[signals["municipality_id"] == muni_id]
        if not muni_signals.empty:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run("Intelligence Alert: ")
            run.font.name = FONT_NAME
            run.bold = True
            run.font.color.rgb = OFA_RED
            run.font.size = Pt(9.5)
            for _, sig in muni_signals.iterrows():
                _body_para(
                    doc,
                    f"{_clean(sig.get('trigger_keyword'))} ({sig.get('category', '')}) "
                    f"— {_clean(sig.get('discovered_date'))}",
                    space_after=Pt(2),
                    size=Pt(9),
                )

        doc.add_paragraph("")

    doc.add_page_break()


def _add_intelligence_section(doc, data):
    """Scanner intelligence alerts with full untruncated summaries."""
    signals = data["signals"]

    _heading(doc, "Intelligence Alerts")

    if signals.empty:
        _body_para(doc, "No recent scanner signals detected.")
        doc.add_page_break()
        return

    _body_para(
        doc,
        f"{len(signals)} scanner signal(s) detected. These are municipalities where "
        f"council agendas or minutes mentioned OFA-tracked bylaw keywords.",
    )

    headers = ["Municipality", "Category", "Keyword", "Date", "Summary / Snippet"]
    rows = []
    for _, sig in signals.iterrows():
        ai = _clean(sig.get("ai_summary"))
        if ai == "—":
            ai = _clean(sig.get("snippet"))
        kw_text = _clean(sig.get("trigger_keyword"))
        src_url = _valid_url(sig.get("source_url"))
        kw_cell = {"text": kw_text, "url": src_url} if (src_url and kw_text != "—") else kw_text

        rows.append([
            _clean(sig.get("municipality_name", sig.get("munid_raw"))),
            CATEGORY_NAMES.get(sig.get("category", ""), _clean(sig.get("category"))),
            kw_cell,
            _clean(sig.get("discovered_date")),
            ai,
        ])

    _add_table(
        doc,
        headers,
        rows,
        col_widths=[1.15, 1.05, 1.05, 0.80, 2.95],
        center_cols=[3],
    )
    doc.add_page_break()


def _add_advocacy_matrix(doc, data):
    """Priority ranking with auto-generated recommended actions."""
    bylaws = data["bylaws"]
    signals = data["signals"]
    munis = data["municipalities"]
    scope = data["scope"]

    _heading(doc, "Advocacy Priority Matrix")
    _body_para(
        doc,
        "Municipalities ranked by advocacy urgency. Scoring: missing exemptions (3 pts), "
        "partial / statutory-only exemptions (2 pts), expired bylaws (5 pts), "
        "expiring within 18 months (3 pts), scanner signals (2 pts), "
        "unknown status (1 pt). Recommended actions are auto-generated.",
    )

    today = datetime.date.today()
    scored = []

    for _, muni in munis.iterrows():
        muni_id = muni["id"]
        muni_name = muni["name"]
        mb = bylaws[bylaws["municipality_id"] == muni_id]
        ms = signals[signals["municipality_id"] == muni_id] if not signals.empty else pd.DataFrame()

        score = 0
        no_cats, partial_cats, expired_cats, expiring_cats, unknown_cats = [], [], [], [], []

        for _, b in mb.iterrows():
            status = _resolve(b["exemption_status"])
            cat_label = CATEGORY_NAMES.get(b["category"], b["category"])

            if status == "No":
                no_cats.append(cat_label)
                score += 3
            elif status == "Partial":
                partial_cats.append(cat_label)
                score += 2
            elif status in ("Not Known", "NOT KNOWN", "No explicit exemption found", "—"):
                unknown_cats.append(cat_label)
                score += 1

            expiry = str(b.get("expiry_date", "") or "").strip()
            if expiry:
                try:
                    exp_date = pd.to_datetime(expiry).date()
                    if exp_date < today:
                        expired_cats.append(cat_label)
                        score += 5
                    elif (exp_date - today).days <= 540:
                        expiring_cats.append(cat_label)
                        score += 3
                except Exception:
                    pass

        if not ms.empty:
            score += 2 * len(ms)

        if score == 0:
            continue

        if expired_cats:
            action = f"Monitor renewal — request exemption ({', '.join(expired_cats)})"
        elif no_cats:
            action = f"Send template letter ({', '.join(no_cats)})"
        elif expiring_cats:
            action = f"Engage before renewal ({', '.join(expiring_cats)})"
        elif partial_cats:
            action = f"Request full NFP exemption ({', '.join(partial_cats)})"
        elif not ms.empty:
            kw = _clean(ms.iloc[0].get("trigger_keyword", "activity"))
            action = f"Review council activity — '{kw}'"
        elif unknown_cats:
            action = f"Research needed ({', '.join(unknown_cats)})"
        else:
            action = "Monitor"

        scored.append({
            "name": muni_name,
            "score": score,
            "no": len(no_cats),
            "expired": len(expired_cats),
            "expiring": len(expiring_cats),
            "signals": len(ms),
            "action": action,
        })

    if not scored:
        _body_para(doc, "No advocacy priorities identified.")
        return

    scored.sort(key=lambda x: x["score"], reverse=True)

    if scope == "provincial":
        scored = scored[:30]
        _body_para(doc, "Showing top 30 priority municipalities.")

    headers = ["Municipality", "Priority", "No Exempt.", "Expired", "Expiring", "Signals", "Recommended Action"]
    rows = []
    for s in scored:
        pri = "Critical" if s["score"] >= 10 else "High" if s["score"] >= 5 else "Monitor"
        rows.append([
            s["name"],
            pri,
            str(s["no"]) if s["no"] else "—",
            str(s["expired"]) if s["expired"] else "—",
            str(s["expiring"]) if s["expiring"] else "—",
            str(s["signals"]) if s["signals"] else "—",
            s["action"],
        ])

    table = _add_table(
        doc,
        headers,
        rows,
        col_widths=[1.30, 0.72, 0.70, 0.62, 0.64, 0.60, 2.42],
        center_cols=[1, 2, 3, 4, 5],
    )

    for i, s in enumerate(scored):
        bg = RED_BG if s["score"] >= 10 else AMBER_BG if s["score"] >= 5 else GREEN_BG
        _set_cell_shading(table.rows[i + 1].cells[1], bg)

    doc.add_page_break()


def _add_methodology(doc, data, include_full_wordings=True):
    """Data sources and definitions."""
    _heading(doc, "Methodology & Data Notes")

    _body_para(
        doc,
        f"Generated on {datetime.date.today().strftime('%B %d, %Y')} from the "
        f"Ontario Federation of Agriculture Municipal Bylaw Database.",
    )

    if data["scope"] != "provincial":
        if include_full_wordings:
            _body_para(
                doc,
                "This report pairs compact comparison tables (showing exemption status, bylaw names with direct "
                "document links, dates, and structured yes/no provisions) with full-width verbatim wording blocks "
                "displaying every tracked exemption clause, definition, limit, expiry note, and researcher note "
                "without truncation.",
            )
        else:
            _body_para(
                doc,
                "This summary edition displays compact comparison tables only. Enable 'Include full verbatim bylaw "
                "wordings & notes' in the Report Generator to print complete tracked clauses and notes.",
            )

    _heading(doc, "Categories Tracked", level=2)
    for cat in CATEGORY_ORDER:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(CATEGORY_NAMES[cat])
        r.font.name = FONT_NAME
        r.font.size = Pt(9.5)
        r.font.color.rgb = DARK_TEXT

    _heading(doc, "Exemption Status Definitions", level=2)
    for status, desc in [
        ("Yes", "An explicit, full farm or normal farm practice exemption exists in the bylaw."),
        ("Partial", "Statutory minimum or narrow carve-out only (e.g. Site Alteration bylaws that exempt only Drainage Act works and incidental topsoil removal under Municipal Act s. 142(5)–(6), meaning farm fill placement and grading may still require a permit)."),
        ("No", "The bylaw applies to farms with no exemption provision."),
        ("N/A", "The municipality does not have this type of bylaw."),
        ("NOT KNOWN", "Research has not yet confirmed the exemption status."),
    ]:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        r_b = p.add_run(f"{status}: ")
        r_b.font.name = FONT_NAME
        r_b.font.size = Pt(9.5)
        r_b.bold = True
        r_b.font.color.rgb = OFA_BLUEWOOD
        r_d = p.add_run(desc)
        r_d.font.name = FONT_NAME
        r_d.font.size = Pt(9.5)
        r_d.font.color.rgb = DARK_TEXT

    _heading(doc, "Priority Scoring", level=2)
    for item in [
        "Missing exemption (No): 3 points per category",
        "Partial / statutory-only exemption (Partial): 2 points per category",
        "Expired bylaw: 5 points per category",
        "Expiring within 18 months: 3 points per category",
        "Scanner signal detected: 2 points per signal",
        "Unknown status: 1 point per category",
    ]:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(item)
        r.font.name = FONT_NAME
        r.font.size = Pt(9.5)
        r.font.color.rgb = DARK_TEXT

    doc.add_paragraph("")
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    run = p.add_run("Disclaimer: ")
    run.font.name = FONT_NAME
    run.font.size = Pt(9)
    run.bold = True
    run.font.color.rgb = OFA_BLUEWOOD
    r_disc = p.add_run(
        "This report is for informational purposes. Bylaw data may change between "
        "database updates. Always consult the original municipal bylaw documents."
    )
    r_disc.font.name = FONT_NAME
    r_disc.font.size = Pt(9)
    r_disc.font.color.rgb = MUTED_TEXT


# ══════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════

def generate_report(scope="provincial", scope_value=None, include_full_wordings=True):
    """Generate a complete OFA-branded DOCX report.

    Args:
        scope: 'provincial', 'county', or 'municipality'
        scope_value: County name or municipality name
        include_full_wordings: When True (default), prints full untruncated
            verbatim bylaw wordings, definitions, limits, and notes beneath
            each category's compact comparison tables.

    Returns:
        BytesIO containing the generated DOCX file.
    """
    conn = get_connection()
    data = get_report_data(conn, scope, scope_value)
    conn.close()

    doc = Document()

    # Global font defaults (OFA Brand Guide 2025-26: Arial for Word)
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = Pt(10)
    style.font.color.rgb = DARK_TEXT

    _configure_page_and_footer(doc)

    _add_cover_page(doc, scope, scope_value, include_full_wordings=include_full_wordings)
    _add_executive_summary(doc, data)

    for cat_code in CATEGORY_ORDER:
        _add_category_section(doc, data, cat_code, include_full_wordings=include_full_wordings)

    if scope == "county":
        _add_municipality_profiles(doc, data)

    _add_intelligence_section(doc, data)
    _add_advocacy_matrix(doc, data)
    _add_methodology(doc, data, include_full_wordings=include_full_wordings)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# ══════════════════════════════════════════════════════════════
# Additive Helper: 1–2 Page OFA Council Fee Comparison Brief
# (Used exclusively by pages/7_🧮_Fee_Explorer.py; leaves generate_report untouched)
# ══════════════════════════════════════════════════════════════

def generate_fee_comparison_brief(
    focus_muni: str,
    peer_munis: list[str],
    topic: str = "bldg_fees",
    bldg_sqft: int = 10000,
    is_livestock: bool = True,
    assumed_cost_per_sqft: float | None = None,
    sa_volume_m3: int = 15000,
) -> io.BytesIO:
    """Generate a concise 1–2 page OFA-branded Council Delegation Fee Comparison Brief (.docx).

    Args:
        focus_muni: Primary municipality being spotlighted (highlighted in OFA Crimson tint).
        peer_munis: Ordered list of comparator municipalities (including or excluding focus_muni).
        topic: 'bldg_fees', 'site_alt', or 'combined'.
        bldg_sqft: Reference farm building footprint in sq. ft.
        is_livestock: True for Livestock Barn, False for Equipment / Drive Shed.
        assumed_cost_per_sqft: Optional $/ft² assumption applied ONLY to valuation-based BLDG_FEES rows.
        sa_volume_m3: Reference imported clean topsoil/fill volume in m³.
    """
    from db_utils import get_category_summary
    from bldg_fees_calc import evaluate_bldg_fee
    from site_alt_fees_calc import evaluate_site_alt_fee

    target_munis = [focus_muni] + [m for m in peer_munis if m != focus_muni]
    conn = get_connection()
    bf_all = get_category_summary(conn, "BLDG_FEES") if topic in ("bldg_fees", "combined") else pd.DataFrame()
    sa_all = get_category_summary(conn, "SITE_ALT") if topic in ("site_alt", "combined") else pd.DataFrame()
    conn.close()

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = Pt(9.5)
    style.font.color.rgb = DARK_TEXT
    _configure_page_and_footer(doc)

    # Compact OFA Header Banner (Logo + Title on page 1 — handout ready, no cover page bloat)
    hdr_tbl = doc.add_table(rows=1, cols=2)
    hdr_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_fixed_width(hdr_tbl, [1.55, 5.45])
    c_logo, c_title = hdr_tbl.rows[0].cells
    _set_cell_margins(c_logo, top=40, bottom=40, left=40, right=60)
    _set_cell_margins(c_title, top=40, bottom=40, left=80, right=40)
    if os.path.exists(LOGO_PATH):
        p_logo = c_logo.paragraphs[0]
        p_logo.add_run().add_picture(LOGO_PATH, width=Inches(1.35))
    else:
        _set_cell(c_logo, "OFA", bold=True, size=Pt(14), color=OFA_CRIMSON)

    topic_titles = {
        "bldg_fees": "Municipal Farm Building Permit Fee Comparison Brief",
        "site_alt": "Municipal Site Alteration & Excess Soil Fee Comparison Brief",
        "combined": "Municipal Farm Permit & Excess Soil Fee Comparison Brief",
    }
    p_t = c_title.paragraphs[0]
    p_t.paragraph_format.space_after = Pt(2)
    rt = p_t.add_run(topic_titles.get(topic, topic_titles["bldg_fees"]))
    rt.font.name = FONT_NAME
    rt.font.size = Pt(14)
    rt.bold = True
    rt.font.color.rgb = OFA_BLUEWOOD

    p_sub = c_title.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(0)
    rs = p_sub.add_run(
        f"Prepared for {focus_muni} Council Delegation · {len(target_munis)} Municipalities Compared · "
        f"Ontario Federation of Agriculture · {datetime.date.today().strftime('%B %d, %Y')}"
    )
    rs.font.name = FONT_NAME
    rs.font.size = Pt(8.5)
    rs.font.color.rgb = MUTED_TEXT

    # Accent divider line
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(2)
    p_div.paragraph_format.space_after = Pt(8)
    _set_paragraph_shading_and_border(p_div, bottom_border_hex=VALENCIA_HEX)

    def _add_callout(label_txt: str, body_txt: str, border_hex: str = HEADER_BG):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Inches(0.06)
        _set_paragraph_shading_and_border(p, fill_hex=WARM_TINT_BG, left_border_hex=border_hex, left_sz="18")
        r1 = p.add_run(f"{label_txt}: ")
        r1.font.name = FONT_NAME
        r1.font.size = Pt(9)
        r1.bold = True
        r1.font.color.rgb = OFA_BLUEWOOD
        r2 = p.add_run(_sanitize_xml(body_txt))
        r2.font.name = FONT_NAME
        r2.font.size = Pt(9)
        r2.font.color.rgb = DARK_TEXT

    def _fmt_d(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        return f"${round(float(val)):,}"

    # ── SECTION A: FARM BUILDING PERMIT FEES ──
    if topic in ("bldg_fees", "combined") and not bf_all.empty:
        struct_lbl = "Livestock Barn" if is_livestock else "Equipment / Drive Shed"
        h_bf = doc.add_paragraph()
        h_bf.paragraph_format.space_before = Pt(4)
        h_bf.paragraph_format.space_after = Pt(3)
        rh = h_bf.add_run(f"Farm Building Permit Fees — {bldg_sqft:,} sq. ft. {struct_lbl}")
        rh.font.name = FONT_NAME
        rh.font.size = Pt(11.5)
        rh.bold = True
        rh.font.color.rgb = OFA_CRIMSON

        # Compute provincial median on area/stepped farm schedules
        _prov_vals = []
        for _, _pr in bf_all.iterrows():
            _pv = evaluate_bldg_fee(_pr, float(bldg_sqft), is_livestock=is_livestock, assumed_cost_per_sqft=None)
            if _pv is not None and str(_pr.get("name", "")) != "Moosonee":
                _prov_vals.append(_pv)
        prov_med = float(pd.Series(_prov_vals).median()) if _prov_vals else None

        sub_bf = bf_all[bf_all["name"].isin(target_munis)].copy()
        rows_data = []
        focus_row = None
        for nm in target_munis:
            m_df = sub_bf[sub_bf["name"] == nm]
            if m_df.empty:
                continue
            r = m_df.iloc[0]
            est = evaluate_bldg_fee(r, float(bldg_sqft), is_livestock=is_livestock, assumed_cost_per_sqft=assumed_cost_per_sqft)
            est_base = evaluate_bldg_fee(r, float(bldg_sqft), is_livestock=is_livestock, assumed_cost_per_sqft=None)
            is_val_est = (est is not None and est_base is None and assumed_cost_per_sqft is not None)
            item = {
                "name": nm,
                "area": _clean(r.get("geographic_area")),
                "est": est,
                "est_disp": (f"{_fmt_d(est)} (Est.)" if is_val_est else _fmt_d(est)) if est is not None else _clean(r.get("pricing_model"), max_len=28),
                "eff_disp": f"${est / bldg_sqft:.2f}/ft²" if est is not None else "—",
                "year": str(int(float(r["fee_year"]))) if pd.notna(r.get("fee_year")) and str(r.get("fee_year")).strip() else "—",
                "model": _clean(r.get("pricing_model"), max_len=36, single_line=True),
                "bylaw": _clean(r.get("bylaw_name"), max_len=48, single_line=True),
                "url": _valid_url(r.get("bylaw_link")),
                "deposit": _clean(r.get("refundable_deposit"), single_line=True),
                "formula": _clean(r.get("formula_notes"), single_line=True),
            }
            rows_data.append(item)
            if nm == focus_muni:
                focus_row = item

        # Sort priced rows high-to-low, then non-priced
        rows_data.sort(key=lambda x: (x["est"] is None, -(x["est"] or 0.0), x["name"]))

        if focus_row:
            if focus_row["est"] is not None and prov_med:
                pct_diff = round((focus_row["est"] - prov_med) / prov_med * 100)
                rel = f"{abs(pct_diff)}% {'above' if pct_diff > 0 else 'below'} the Ontario area-based median ({_fmt_d(prov_med)})" if pct_diff != 0 else f"equal to the Ontario median ({_fmt_d(prov_med)})"
                _add_callout(
                    f"{focus_muni} Snapshot",
                    f"Estimated non-refundable permit fee of {focus_row['est_disp']} ({focus_row['eff_disp']}) — {rel}. "
                    f"Formula notes: {focus_row['formula']} | Deposits/Surcharges: {focus_row['deposit']}.",
                    border_hex=VALENCIA_HEX,
                )
            else:
                _add_callout(
                    f"{focus_muni} Snapshot",
                    f"Pricing model: {focus_row['model']}. {focus_row['formula']}",
                    border_hex=VALENCIA_HEX,
                )

        if assumed_cost_per_sqft is not None:
            p_assump = doc.add_paragraph()
            p_assump.paragraph_format.space_after = Pt(4)
            ra = p_assump.add_run(
                f"Note: Rows marked '(Est.)' use a user-selected construction value assumption of ${round(assumed_cost_per_sqft):,}/ft² applied solely to valuation-based ($/$1,000 CV) schedules."
            )
            ra.font.name = FONT_NAME
            ra.font.size = Pt(8)
            ra.italic = True
            ra.font.color.rgb = MUTED_TEXT

        widths = [1.45, 0.90, 0.78, 0.45, 1.52, 1.90]
        tbl = doc.add_table(rows=1 + len(rows_data), cols=6)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_fixed_width(tbl, widths)
        _set_table_borders(tbl)
        hdrs = ["Municipality", f"{bldg_sqft:,} ft² Fee", "Eff. Rate", "Year", "Pricing Model", "Source By-law"]
        _set_row_header(tbl.rows[0])
        _set_row_cant_split(tbl.rows[0])
        for ci, htxt in enumerate(hdrs):
            cell = tbl.rows[0].cells[ci]
            _set_cell_shading(cell, HEADER_BG)
            _set_cell_margins(cell, top=55, bottom=55, left=65, right=65)
            _set_cell(cell, htxt, bold=True, size=Pt(8.5), color=WHITE)

        for ri, it in enumerate(rows_data, start=1):
            row = tbl.rows[ri]
            _set_row_cant_split(row)
            is_f = (it["name"] == focus_muni)
            bg = "FDECEC" if is_f else (WARM_TINT_BG if ri % 2 == 0 else None)
            bylaw_val = {"text": it["bylaw"], "url": it["url"]} if it["url"] else it["bylaw"]
            vals = [it["name"], it["est_disp"], it["eff_disp"], it["year"], it["model"], bylaw_val]
            for ci, v in enumerate(vals):
                cell = row.cells[ci]
                if bg:
                    _set_cell_shading(cell, bg)
                _set_cell_margins(cell, top=45, bottom=45, left=65, right=65)
                _set_cell(
                    cell,
                    v,
                    bold=(is_f and ci in (0, 1)),
                    size=Pt(8.2),
                    color=(OFA_CRIMSON if (is_f and ci in (0, 1)) else DARK_TEXT),
                    align=(WD_ALIGN_PARAGRAPH.RIGHT if ci in (1, 2, 3) else None),
                )

        _add_callout(
            "Statutory Context (Building Code Act, 1992, s. 7)",
            "Section 7(2) caps total building permit fees at reasonable municipal cost recovery (fees cannot fund general revenue). "
            "Section 7(4)–(8) requires annual public Building Reserve Fund reporting and advance public notice + cost justification before fee increases.",
            border_hex=HEADER_BG,
        )

    # ── SECTION B: SITE ALTERATION & EXCESS SOIL FEES ──
    if topic in ("site_alt", "combined") and not sa_all.empty:
        h_sa = doc.add_paragraph()
        h_sa.paragraph_format.space_before = Pt(8 if topic == "combined" else 4)
        h_sa.paragraph_format.space_after = Pt(3)
        rh = h_sa.add_run(f"Site Alteration & Excess Soil Fees — {sa_volume_m3:,} m³ (~{sa_volume_m3 // 10:,} Tri-Axle Loads)")
        rh.font.name = FONT_NAME
        rh.font.size = Pt(11.5)
        rh.bold = True
        rh.font.color.rgb = OFA_CRIMSON

        sub_sa = sa_all[sa_all["name"].isin(target_munis)].copy()
        sa_rows = []
        sa_focus = None
        for nm in target_munis:
            m_df = sub_sa[sub_sa["name"] == nm]
            if m_df.empty:
                continue
            r = m_df.iloc[0]
            est = evaluate_site_alt_fee(r, float(sa_volume_m3))
            pm = _clean(r.get("fee_pricing_model"), single_line=True)
            fvs = _clean(r.get("fee_verification_status"), single_line=True)
            if est is not None:
                est_disp = "$0 (Exempt)" if est <= 0 else _fmt_d(est)
            elif "hectare" in pm.lower():
                est_disp = "Per Hectare"
            elif "no bylaw" in fvs.lower():
                est_disp = "No Bylaw ($0)"
            else:
                est_disp = fvs if fvs != "—" else "—"
            item = {
                "name": nm,
                "exempt": _resolve(r.get("exemption_status")),
                "ag_fee": _clean(r.get("ag_import_fee_status"), max_len=24, single_line=True),
                "est": est,
                "est_disp": est_disp,
                "ban": _clean(r.get("out_of_muni_fill_ban"), single_line=True),
                "security": _clean(r.get("security_deposit_terms"), max_len=46, single_line=True),
                "peer_rev": _clean(r.get("peer_review_recovery"), single_line=True),
                "bylaw": _clean(r.get("fees_bylaw_name") or r.get("bylaw_name"), max_len=44, single_line=True),
                "url": _valid_url(r.get("fees_bylaw_link")) or _valid_url(r.get("bylaw_link")),
                "formula": _clean(r.get("fee_formula_notes"), single_line=True),
            }
            sa_rows.append(item)
            if nm == focus_muni:
                sa_focus = item

        sa_rows.sort(key=lambda x: (x["est"] is None, -(x["est"] or -1.0), x["name"]))

        if sa_focus:
            _add_callout(
                f"{focus_muni} Excess Soil Snapshot",
                f"Farm Exemption: {sa_focus['exempt']} · Ag Import Fee Status: {sa_focus['ag_fee']} · "
                f"Est. Permit Fee ({sa_volume_m3:,} m³): {sa_focus['est_disp']} · Out-of-Muni Fill Ban: {sa_focus['ban']}. "
                f"Refundable Securities: {sa_focus['security']} | Peer Review Recovery: {sa_focus['peer_rev']}.",
                border_hex=VALENCIA_HEX,
            )

        widths = [1.30, 0.62, 1.15, 0.88, 1.45, 1.60]
        tbl = doc.add_table(rows=1 + len(sa_rows), cols=6)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_fixed_width(tbl, widths)
        _set_table_borders(tbl)
        hdrs = ["Municipality", "Exemp.", "Ag Import Fee", f"{sa_volume_m3:,} m³ Fee", "Refundable Security", "Source By-law"]
        _set_row_header(tbl.rows[0])
        _set_row_cant_split(tbl.rows[0])
        for ci, htxt in enumerate(hdrs):
            cell = tbl.rows[0].cells[ci]
            _set_cell_shading(cell, HEADER_BG)
            _set_cell_margins(cell, top=55, bottom=55, left=55, right=55)
            _set_cell(cell, htxt, bold=True, size=Pt(8.2), color=WHITE)

        for ri, it in enumerate(sa_rows, start=1):
            row = tbl.rows[ri]
            _set_row_cant_split(row)
            is_f = (it["name"] == focus_muni)
            bg = "FDECEC" if is_f else (WARM_TINT_BG if ri % 2 == 0 else None)
            bylaw_val = {"text": it["bylaw"], "url": it["url"]} if it["url"] else it["bylaw"]
            vals = [it["name"], it["exempt"], it["ag_fee"], it["est_disp"], it["security"], bylaw_val]
            for ci, v in enumerate(vals):
                cell = row.cells[ci]
                if bg:
                    _set_cell_shading(cell, bg)
                _set_cell_margins(cell, top=45, bottom=45, left=55, right=55)
                _set_cell(
                    cell,
                    v,
                    bold=(is_f and ci in (0, 3)),
                    size=Pt(8.0),
                    color=(OFA_CRIMSON if (is_f and ci in (0, 3)) else DARK_TEXT),
                    align=(WD_ALIGN_PARAGRAPH.RIGHT if ci == 3 else None),
                )

        _add_callout(
            "Policy Context (Normal Farm Practice & O. Reg. 406/19)",
            "OFA advocates for clear agricultural exemptions for normal farm practices under the FFPPA and provincial excess soil rules "
            "(O. Reg. 406/19) that place soil-quality testing responsibility on the generator rather than imposing punitive volumetric fees or retainers on receiving farms.",
            border_hex=HEADER_BG,
        )

    p_src = doc.add_paragraph()
    p_src.paragraph_format.space_before = Pt(6)
    r_s = p_src.add_run(
        "Source: Ontario Federation of Agriculture Municipal Bylaw Database (primary-source audited municipal by-laws & user fee schedules). "
        "Non-refundable permit fees are reported separately from refundable securities, deposits, and peer-review retainers. Always verify current schedules with the municipal clerk."
    )
    r_s.font.name = FONT_NAME
    r_s.font.size = Pt(7.8)
    r_s.font.color.rgb = MUTED_TEXT

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
