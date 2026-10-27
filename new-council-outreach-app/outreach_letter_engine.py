"""
outreach_letter_engine.py — Generates post-election congratulatory & agricultural profile
letters (.docx, plain text preview, mailto links, and bulk county .zip packages).
"""

import io
import datetime
import urllib.parse
import zipfile
import re
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def fmt_currency_large(val):
    """Format large dollar figures cleanly (e.g., $1.47 billion or $384.9 million)."""
    if val is None:
        return "N/A"
    v = float(val)
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:,.2f} billion"
    elif v >= 1_000_000:
        return f"${v / 1_000_000:,.1f} million"
    else:
        return f"${v:,.0f}"


def fmt_gdp_millions(gdp_m):
    """Format OMAFA GDP (stored in millions of chained 2017 dollars)."""
    if gdp_m is None:
        return "N/A"
    v = float(gdp_m)
    if v >= 1000.0:
        return f"${v / 1000.0:,.2f} billion (${v:,.1f} million)"
    else:
        return f"${v:,.1f} million"


def build_letter_sections(
    county_data: dict,
    muni_data: dict,
    sender_name: str,
    sender_title: str,
    federation_name: str,
    contact_email: str = "",
    contact_phone: str = "",
    custom_intro_note: str = "",
    survey_override: dict = None,
    survey_scope_label: str = None,
    num_challenges: int = 4,
    num_priorities: int = 4,
    include_lower_tier_stats: bool = True,
) -> dict:
    """Assemble all structured text blocks for both .docx and plain-text rendering."""
    today_str = datetime.date.today().strftime("%B %d, %Y")
    raw_muni_name = muni_data.get("name", "")
    muni_status = muni_data.get("municipal_status", "")
    address = muni_data.get("address", "")
    county_display = county_data.get("display_name", county_data.get("county_key", ""))
    # For Upper-Tier councils (whose DB name is e.g. 'Huron' or 'Essex'), use full display name ('Huron County')
    muni_name = county_display if muni_status == "Upper Tier" else raw_muni_name

    # Determine appropriate salutation title (Warden vs Mayor/Chair)
    if muni_status == "Upper Tier":
        if "Region" in county_display or "Regional" in county_display or "District" in county_display:
            head_title = "Regional Chair and Members of Council"
        else:
            head_title = "Warden and Members of County Council"
    else:
        head_title = f"Mayor and Members of {muni_name} Council"

    salutation = f"Dear {head_title},"
    subject_line = f"Re: Congratulations to the Newly Elected Council & Introduction from {federation_name}"

    # 1. Opening paragraphs
    p_opening_1 = (
        f"On behalf of {federation_name} and the farm families we represent across {county_display}, "
        f"I would like to extend our sincere congratulations on your election to {muni_name} Council "
        f"for the 2026–2030 municipal term. Serving in municipal government is a vital responsibility, "
        f"and we thank both returning and newly elected members of Council for your commitment to "
        f"public service and the prosperity of our community."
    )

    p_opening_2 = (
        f"{federation_name} is the local voice for farm families and agricultural businesses in {county_display}, "
        f"working in partnership with the Ontario Federation of Agriculture (OFA), which represents more than "
        f"38,000 farm family businesses across the province. Our mission is to work constructively with "
        f"municipal councils and staff to ensure that local policies, bylaws, and infrastructure investments "
        f"support a thriving, sustainable agricultural sector and strong rural communities."
    )
    if custom_intro_note and custom_intro_note.strip():
        p_opening_2 += " " + custom_intro_note.strip()

    # 2. Agricultural Profile (2021 Census of Agriculture)
    cen = county_data.get("census_2021", {})
    total_farms = cen.get("total_farms", 0)
    total_ops = cen.get("total_operators")
    total_acres = cen.get("total_acres", 0)
    crop_acres = cen.get("crop_acres", 0)
    wood_acres = cen.get("woodlands_wetlands_acres", 0)
    receipts = cen.get("gross_farm_receipts", 0)
    capital = cen.get("total_farm_capital", 0)
    direct_farms = cen.get("direct_sales_farms", 0)
    top_sectors = cen.get("top_sectors", [])

    ops_phrase = f" operated by {total_ops:,} farm operators" if total_ops else ""
    wood_phrase = (
        f" and steward {wood_acres:,} acres of on-farm woodlands and wetlands that provide essential watershed, "
        f"flood-mitigation, and environmental benefits"
        if wood_acres and wood_acres > 0 else ""
    )

    census_bullets = [
        (
            f"Farms & Agricultural Land Base ({county_display}): ",
            f"{total_farms:,} farms{ops_phrase} manage {total_acres:,} acres of agricultural land "
            f"(including {crop_acres:,} acres in productive field and horticultural crops){wood_phrase}."
        ),
        (
            f"Farm-Gate Production & Local Capital Investment: ",
            f"Local farms generate {fmt_currency_large(receipts)} in annual gross farm receipts and represent "
            f"{fmt_currency_large(capital)} in total farm capital invested locally in land, buildings, equipment, and livestock."
        ),
    ]

    if top_sectors:
        sec_parts = [f"{s['sector']} ({s['farms']:,} farms)" for s in top_sectors[:4]]
        sec_str = ", ".join(sec_parts[:-1]) + (f", and {sec_parts[-1]}" if len(sec_parts) > 1 else sec_parts[0])
        direct_str = (
            f" In addition, {direct_farms:,} farms sell agricultural products directly to consumers through "
            f"farm-gate stores, stands, farmers' markets, and local food channels."
            if direct_farms and direct_farms > 0 else ""
        )
        census_bullets.append((
            "Leading Agricultural Sectors: ",
            f"Our diverse agricultural production is anchored by {sec_str}.{direct_str}"
        ))

    # Optional lower-tier specific bullet if available
    lt_cen = muni_data.get("lower_tier_census") if include_lower_tier_stats else None
    if lt_cen and lt_cen.get("total_farms") and muni_status == "Lower Tier":
        lt_f = lt_cen["total_farms"]
        lt_a = lt_cen.get("total_acres")
        lt_r = lt_cen.get("gross_farm_receipts")
        lt_parts = [f"{lt_f:,} farms"]
        if lt_a:
            lt_parts.append(f"managing {lt_a:,} acres of farmland")
        if lt_r:
            lt_parts.append(f"generating {fmt_currency_large(lt_r)} in annual gross farm receipts")
        census_bullets.append((
            f"Local Snapshot for {muni_name}: ",
            f"Within {muni_name} specifically, the Census of Agriculture records " + " ".join(lt_parts) + "."
        ))

    # 3. Economic Attribution (OMAFA Model)
    attr = county_data.get("attribution", {})
    gdp_2025 = attr.get("gdp_2025_m", 0)
    jobs_latest = attr.get("jobs_latest", 0)
    is_combined = attr.get("is_combined_cd", False)
    cd_label = attr.get("cd_label", county_display)

    if is_combined:
        p_economic = (
            f"Beyond the farm gate, agriculture anchors a broader agri-food value chain spanning primary farm production, "
            f"food and beverage processing, transportation, and agri-food retail. According to the Ontario Ministry of "
            f"Agriculture, Food and Agribusiness (OMAFA) economic attribution model, the agri-food value chain across the "
            f"{cd_label} generates {fmt_gdp_millions(gdp_2025)} in Gross Domestic Product (GDP, chained 2017 dollars) "
            f"and supports {jobs_latest:,} jobs in our regional economy."
        )
    else:
        p_economic = (
            f"Beyond the farm gate, agriculture anchors a broader local value chain spanning primary farm production, "
            f"food and beverage manufacturing, input supply, and agri-food retail. According to the Ontario Ministry of "
            f"Agriculture, Food and Agribusiness (OMAFA) economic attribution model, the agri-food value chain in "
            f"{county_display} contributes {fmt_gdp_millions(gdp_2025)} in Gross Domestic Product (GDP, chained 2017 dollars) "
            f"and supports {jobs_latest:,} jobs across the community."
        )

    # 4. Top Issues & Policy Priorities (2025 Farm Business Confidence Survey)
    surv = survey_override if survey_override is not None else county_data.get("survey_2025", {})
    s_n = surv.get("n", 0)
    scope_lbl = survey_scope_label or county_display

    challenges = surv.get("challenges", [])[:num_challenges]
    # Combine top overall policy priorities with top municipal-relevant policy priorities
    all_priorities = surv.get("policy_priorities", [])
    muni_priorities = surv.get("municipal_priorities", [])

    # Select top policy priorities ensuring key municipal priorities are represented
    selected_priorities = []
    seen_labels = set()
    for item in all_priorities[:max(2, num_priorities - 2)]:
        selected_priorities.append(item)
        seen_labels.add(item["label"])
    for item in muni_priorities:
        if len(selected_priorities) >= num_priorities:
            break
        if item["label"] not in seen_labels:
            selected_priorities.append(item)
            seen_labels.add(item["label"])
    for item in all_priorities:
        if len(selected_priorities) >= num_priorities:
            break
        if item["label"] not in seen_labels:
            selected_priorities.append(item)
            seen_labels.add(item["label"])

    p_survey_intro = (
        f"Each year, OFA conducts the Farm Business Confidence Survey to hear directly from producers about the "
        f"pressures facing their operations and the policy actions most needed to keep local farms competitive. "
        f"In the 2025 Farm Business Confidence Survey ({scope_lbl}, n={s_n} farm respondents), local producers "
        f"identified the following top operational challenges and policy priorities:"
    )

    challenge_bullets = [
        (f"{c['label']}: ", f"Cited as a top business challenge by {c['pct']:.0f}% of local respondents ({c['count']} of {s_n}).")
        for c in challenges
    ]

    priority_bullets = [
        (f"{p['label']}: ", f"Identified as a key policy priority by {p['pct']:.0f}% of local respondents ({p['count']} of {s_n}).")
        for p in selected_priorities
    ]

    # 5. Closing & Offer to Present Official Delegation
    contact_parts = [p for p in [contact_email.strip(), contact_phone.strip()] if p]
    contact_str = " or ".join(contact_parts) if contact_parts else "our local federation office"

    p_delegation = (
        f"Many of the issues that matter most to farm viability — including rural roads, bridges, and municipal drains, "
        f"fair property tax and development charge policies, land-use planning that protects prime agricultural land, "
        f"and practical municipal bylaws — are shaped directly at the municipal council table. "
        f"{federation_name} would welcome the opportunity to appear as an official delegation before {muni_name} Council "
        f"at an upcoming meeting to introduce our local board, share a brief overview of agriculture in our community, "
        f"and discuss how we can work together over the 2026–2030 council term."
    )

    p_closing = (
        f"Once again, congratulations on your election. Please feel free to reach out to me at {contact_str} "
        f"to coordinate a delegation date or whenever {federation_name} can serve as a resource to Council and staff "
        f"on agricultural and rural matters."
    )

    return {
        "date": today_str,
        "municipality_name": muni_name,
        "county_display": county_display,
        "address": address,
        "salutation": salutation,
        "subject_line": subject_line,
        "p_opening_1": p_opening_1,
        "p_opening_2": p_opening_2,
        "census_heading": f"Agricultural Profile of {county_display} (Statistics Canada Census of Agriculture)",
        "census_bullets": census_bullets,
        "economic_heading": f"Economic Contribution of the Agri-Food Sector (OMAFA Attribution Model)",
        "p_economic": p_economic,
        "survey_heading": f"Top Issues & Priorities for Local Farmers (2025 Farm Business Confidence Survey)",
        "p_survey_intro": p_survey_intro,
        "challenge_bullets": challenge_bullets,
        "priority_bullets": priority_bullets,
        "delegation_heading": "Working Together: Request to Present a Delegation to Council",
        "p_delegation": p_delegation,
        "p_closing": p_closing,
        "sender_name": sender_name.strip() or "[Your Name]",
        "sender_title": sender_title.strip() or "[Your Title]",
        "federation_name": federation_name.strip() or "[County Federation Name]",
        "contact_str": " | ".join(contact_parts),
    }


def render_plain_text(sections: dict) -> str:
    """Render the structured letter sections as clean plain text for preview or copying."""
    lines = [
        sections["date"],
        "",
        sections["municipality_name"],
    ]
    if sections.get("address"):
        lines.append(sections["address"])
    lines.extend([
        "",
        sections["salutation"],
        "",
        sections["subject_line"],
        "",
        sections["p_opening_1"],
        "",
        sections["p_opening_2"],
        "",
        f"--- {sections['census_heading']} ---",
    ])
    for bold_prefix, rest in sections["census_bullets"]:
        lines.append(f"  • {bold_prefix}{rest}")

    lines.extend([
        "",
        f"--- {sections['economic_heading']} ---",
        sections["p_economic"],
        "",
        f"--- {sections['survey_heading']} ---",
        sections["p_survey_intro"],
        "",
        "Top Farm Business Challenges Identified Locally:",
    ])
    for bold_prefix, rest in sections["challenge_bullets"]:
        lines.append(f"  • {bold_prefix}{rest}")

    lines.extend([
        "",
        "Key Policy & Municipal Priorities for Local Producers:",
    ])
    for bold_prefix, rest in sections["priority_bullets"]:
        lines.append(f"  • {bold_prefix}{rest}")

    lines.extend([
        "",
        f"--- {sections['delegation_heading']} ---",
        sections["p_delegation"],
        "",
        sections["p_closing"],
        "",
        "Sincerely,",
        "",
        sections["sender_name"],
        f"{sections['sender_title']}, {sections['federation_name']}",
    ])
    if sections.get("contact_str"):
        lines.append(sections["contact_str"])

    return "\n".join(lines)


def generate_docx(
    sections: dict,
    logo_bytes: bytes | None = None,
    logo_alignment: str = "Left",
    logo_width_inches: float = 2.0,
) -> io.BytesIO:
    """Generate a professionally formatted Word document (.docx) from the letter sections."""
    doc = Document()

    # Set clean 0.85-inch margins so the letter fits comfortably on 1.5–2 pages
    for sec in doc.sections:
        sec.top_margin = Inches(0.8)
        sec.bottom_margin = Inches(0.8)
        sec.left_margin = Inches(0.9)
        sec.right_margin = Inches(0.9)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Optional County Federation Logo at top of letterhead
    if logo_bytes:
        p_logo = doc.add_paragraph()
        p_logo.paragraph_format.space_before = Pt(0)
        p_logo.paragraph_format.space_after = Pt(10)
        align_map = {
            "Left": WD_ALIGN_PARAGRAPH.LEFT,
            "Center": WD_ALIGN_PARAGRAPH.CENTER,
            "Right": WD_ALIGN_PARAGRAPH.RIGHT,
        }
        p_logo.alignment = align_map.get(logo_alignment, WD_ALIGN_PARAGRAPH.LEFT)
        r_logo = p_logo.add_run()
        try:
            r_logo.add_picture(io.BytesIO(logo_bytes), width=Inches(logo_width_inches))
        except Exception:
            # Fallback via Pillow if uploaded image is WEBP or non-standard color mode
            from PIL import Image
            img = Image.open(io.BytesIO(logo_bytes))
            png_buf = io.BytesIO()
            img.save(png_buf, format="PNG")
            png_buf.seek(0)
            r_logo.add_picture(png_buf, width=Inches(logo_width_inches))

    def add_para(text="", bold=False, space_after=6, color=None, font_size=11):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(0)
        if text:
            r = p.add_run(text)
            r.bold = bold
            r.font.size = Pt(font_size)
            if color:
                r.font.color.rgb = RGBColor(*color)
        return p

    def add_section_heading(title_text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(title_text)
        r.bold = True
        r.font.size = Pt(11.5)
        r.font.color.rgb = RGBColor(27, 94, 32)  # OFA Deep Forest Green

    def add_bullet(bold_prefix, text_rest):
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(3)
        r1 = p.add_run(bold_prefix)
        r1.bold = True
        r1.font.size = Pt(10.5)
        r2 = p.add_run(text_rest)
        r2.font.size = Pt(10.5)

    # Header / Date / Recipient Address
    add_para(sections["date"], space_after=8)
    add_para(sections["municipality_name"], bold=True, space_after=2)
    if sections.get("address"):
        add_para(sections["address"], space_after=10)
    else:
        p_spacer = doc.add_paragraph()
        p_spacer.paragraph_format.space_after = Pt(6)

    add_para(sections["salutation"], space_after=8)
    add_para(sections["subject_line"], bold=True, space_after=8, color=(27, 94, 32))

    # Opening
    add_para(sections["p_opening_1"], space_after=6)
    add_para(sections["p_opening_2"], space_after=6)

    # Section 1: Census Profile
    add_section_heading(sections["census_heading"])
    for b_pre, b_rest in sections["census_bullets"]:
        add_bullet(b_pre, b_rest)

    # Section 2: Economic Attribution
    add_section_heading(sections["economic_heading"])
    add_para(sections["p_economic"], space_after=6)

    # Section 3: 2025 Survey
    add_section_heading(sections["survey_heading"])
    add_para(sections["p_survey_intro"], space_after=4)

    add_para("Top Farm Business Challenges Identified Locally:", bold=True, space_after=2, font_size=10.5)
    for b_pre, b_rest in sections["challenge_bullets"]:
        add_bullet(b_pre, b_rest)

    add_para("Key Policy & Municipal Priorities for Local Producers:", bold=True, space_after=2, font_size=10.5)
    for b_pre, b_rest in sections["priority_bullets"]:
        add_bullet(b_pre, b_rest)

    # Section 4: Delegation Request & Closing
    add_section_heading(sections["delegation_heading"])
    add_para(sections["p_delegation"], space_after=6)
    add_para(sections["p_closing"], space_after=10)

    # Sign-off
    add_para("Sincerely,", space_after=16)
    add_para(sections["sender_name"], bold=True, space_after=2)
    add_para(f"{sections['sender_title']}, {sections['federation_name']}", space_after=2)
    if sections.get("contact_str"):
        add_para(sections["contact_str"], space_after=2, color=(90, 90, 90), font_size=10)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_email_subject(municipality_name: str, federation_name: str) -> str:
    return f"Congratulations to the 2026–2030 Council & Delegation Request — {federation_name} — {municipality_name}"


def build_cover_email_body(
    sender_name: str,
    sender_title: str,
    federation_name: str,
    municipality_name: str,
    county_display: str,
    contact_str: str = "",
) -> str:
    sig_contact = f"\n{contact_str}" if contact_str else ""
    return (
        f"Dear Municipal Clerk and Members of Council of {municipality_name},\n\n"
        f"Please find attached a letter from {federation_name} congratulating the newly elected "
        f"and returning members of {municipality_name} Council on the 2026–2030 municipal term.\n\n"
        f"Our letter shares a snapshot of the local agricultural profile in {county_display} "
        f"(from the Statistics Canada Census of Agriculture), the economic and employment contribution "
        f"of our local agri-food value chain (from OMAFA's economic attribution model), and the top "
        f"issues and municipal priorities identified by local farmers in OFA's 2025 Farm Business "
        f"Confidence Survey.\n\n"
        f"We kindly ask that this correspondence be included on an upcoming Council agenda, and we "
        f"would welcome the opportunity to appear as an official delegation before Council early in "
        f"the new term to introduce our local federation board and discuss areas where we can work "
        f"together to support local agriculture.\n\n"
        f"Thank you for your assistance and consideration.\n\n"
        f"Sincerely,\n\n"
        f"{sender_name}\n"
        f"{sender_title}\n"
        f"{federation_name}{sig_contact}"
    )


def generate_mailto_link(recipient_email: str, subject: str, body_text: str) -> str:
    MAX_URL_LENGTH = 1900
    encoded_subject = urllib.parse.quote(subject, safe="")
    base = f"mailto:{recipient_email}?subject={encoded_subject}&body="
    remaining = MAX_URL_LENGTH - len(base)
    encoded_body = urllib.parse.quote(body_text, safe="")
    if len(encoded_body) > remaining:
        safe_length = remaining // 3
        truncated = body_text[:safe_length].rsplit(" ", 1)[0]
        truncated += "\n\n[... Please see attached .docx letter for full text ...]"
        encoded_body = urllib.parse.quote(truncated, safe="")
    return f"mailto:{recipient_email}?subject={encoded_subject}&body={encoded_body}"
