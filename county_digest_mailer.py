"""
county_digest_mailer.py — OFA-Branded Outlook-Safe HTML Renderer & Automated Monday Mailer
for County Federation Weekly Municipal Council Digests.

Adheres strictly to OFA Brand Identity Guidelines (2025-26):
  - Fonts: Arial Bold / Arial Regular (official Outlook/Office system font)
  - Palette: Valencia (#DC4949), Crimson (#D7182A), Pickled Bluewood (#334B58),
             Tulip Tree (#ECA842), Champagne (#EDE6DE), Black (#000000)
  - Logo: Full-colour unstretched OFA_logo.png on white header with clear space
  - Footer: OFA CTA Bar + Contact Bar (ofa.on.ca // Tel: 519-821-8883 / 1-800-668-3276)
            and brand promise "Farms and Food Forever."

Usage:
  python county_digest_mailer.py                                  # Run all active subscriptions (Monday automated)
  python county_digest_mailer.py --dry-run                        # Render HTML archives locally without sending
  python county_digest_mailer.py --subscription-id 1 --test-to ben.lefort@ofa.on.ca
"""

from __future__ import annotations

import argparse
import base64
import datetime
import html
import io
import os
import re
import smtplib
import tomllib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from county_digest_engine import (
    DEFAULT_CACHE_PATH,
    build_county_digest_payload,
    format_areas_human,
    load_cached_council_docs,
    parse_geographic_areas,
)
from db_utils import (
    DEFAULT_BCC_EMAIL,
    ensure_digest_tables,
    get_cli_connection,
    get_county_subscription,
    get_municipalities,
    get_sent_content_hashes,
    list_county_subscriptions,
    record_digest_sent,
)
from shared_config import build_keyword_regex

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_FILE = os.path.join(SCRIPT_DIR, ".streamlit", "secrets.toml")
LOGO_PATH = os.path.join(SCRIPT_DIR, "OFA_logo.png")
DIGEST_ARCHIVE_DIR = os.path.join(SCRIPT_DIR, "signals", "county_digests")

# Official OFA Brand Guide 2025-26 HEX Palette
OFA_VALENCIA = "#DC4949"
OFA_CRIMSON = "#D7182A"
OFA_BLUEWOOD = "#334B58"
OFA_TULIP = "#ECA842"
OFA_CHAMPAGNE = "#EDE6DE"
OFA_BLACK = "#000000"


def load_smtp_settings() -> dict[str, Any]:
    """Load Office 365 SMTP credentials from env vars or .streamlit/secrets.toml."""
    server = os.environ.get("SMTP_SERVER", "").strip()
    port_raw = os.environ.get("SMTP_PORT", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()

    if password == "YOUR_APP_PASSWORD_HERE":
        password = ""

    if (not password or not user or not server) and os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, "rb") as fh:
                secrets = tomllib.load(fh)
            smtp_tbl = secrets.get("smtp", {})
            if isinstance(smtp_tbl, dict):
                server = server or str(smtp_tbl.get("server", "")).strip()
                if not port_raw and smtp_tbl.get("port") is not None:
                    port_raw = str(smtp_tbl.get("port")).strip()
                user = user or str(smtp_tbl.get("username", "")).strip()
                if not password:
                    password = str(smtp_tbl.get("password", "")).strip()
        except Exception:
            pass

    # Fallback to st.secrets when running on Streamlit Cloud
    if not password or not user:
        try:
            import streamlit as st
            smtp_tbl = st.secrets.get("smtp", {})
            if smtp_tbl:
                server = server or str(smtp_tbl.get("server", "")).strip()
                if not port_raw and smtp_tbl.get("port") is not None:
                    port_raw = str(smtp_tbl.get("port")).strip()
                user = user or str(smtp_tbl.get("username", "")).strip()
                if not password:
                    password = str(smtp_tbl.get("password", "")).strip()
        except Exception:
            pass

    server = server or "smtp.office365.com"
    try:
        port = int(port_raw) if port_raw else 587
    except ValueError:
        port = 587

    return {
        "server": server,
        "port": port,
        "username": user,
        "password": password,
        "configured": bool(user and password),
    }


def _prepare_trimmed_logo_bytes() -> bytes | None:
    """Trim excess top/bottom whitespace from square OFA_logo.png while preserving exact 1:1 aspect ratio
    and Brand Guide clear space (never stretching or modifying the logo itself)."""
    if not os.path.exists(LOGO_PATH):
        return None
    try:
        from PIL import Image, ImageChops

        im = Image.open(LOGO_PATH).convert("RGBA")
        # Composite onto white background so transparency renders cleanly in Outlook dark/light modes
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(bg, im).convert("RGB")
        white_ref = Image.new("RGB", flat.size, (255, 255, 255))
        diff = ImageChops.difference(flat, white_ref)
        bbox = diff.getbbox()
        if bbox:
            pad_x = 18
            pad_y = 18
            x0 = max(0, bbox[0] - pad_x)
            y0 = max(0, bbox[1] - pad_y)
            x1 = min(flat.width, bbox[2] + pad_x)
            y1 = min(flat.height, bbox[3] + pad_y)
            flat = flat.crop((x0, y0, x1, y1))
        buf = io.BytesIO()
        flat.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        try:
            with open(LOGO_PATH, "rb") as fh:
                return fh.read()
        except Exception:
            return None


def _parse_email_list(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[;,\n]+", str(raw))
    seen = set()
    out = []
    for p in parts:
        addr = p.strip()
        if addr and "@" in addr and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def _highlight_keywords_html(text: str, keywords: list[str]) -> str:
    """Escape raw verbatim discussion text to safe HTML, preserve paragraphs, and highlight matched keywords."""
    if not text:
        return ""
    escaped = html.escape(text)
    sorted_kws = sorted([k for k in keywords if str(k).strip()], key=len, reverse=True)
    for kw in sorted_kws:
        pat = build_keyword_regex(kw)
        escaped = pat.sub(
            lambda m: (
                f'<strong style="background-color:#FCE4C8; color:{OFA_BLACK}; '
                f'padding:1px 3px; border-radius:2px;">{m.group(0)}</strong>'
            ),
            escaped,
        )
    # Convert double newlines to paragraph breaks and single newlines to <br>
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", escaped) if p.strip()]
    html_paras = []
    for p in paragraphs:
        p_br = p.replace("\n", "<br>")
        html_paras.append(f'<p style="margin:0 0 10px 0; line-height:1.55;">{p_br}</p>')
    return "".join(html_paras)


def _badge_colors(status_badge: str) -> tuple[str, str]:
    """Return (bg_hex, text_hex) from OFA Brand Guide palette based on item status."""
    low = str(status_badge or "").lower()
    if any(k in low for k in ("upcoming", "public meeting", "notice")):
        return OFA_TULIP, OFA_BLACK
    if any(k in low for k in ("by-law", "bylaw", "enacted")):
        return OFA_VALENCIA, "#FFFFFF"
    return OFA_BLUEWOOD, "#FFFFFF"


def render_county_digest_html(
    payload: dict[str, Any],
    logo_mode: str = "cid",
    is_test_banner: bool = False,
) -> tuple[str, str]:
    """Render (subject_line, outlook_safe_html) strictly adhering to OFA Brand Guide 2025-26.

    logo_mode:
      - 'cid'   : uses src="cid:ofa_logo" (for SMTP emails with MIMEImage attachment)
      - 'inline': uses base64 data URI (for browser / Streamlit preview & saved HTML drafts)
    """
    fed_name = str(payload.get("federation_name") or "County Federation of Agriculture").strip()
    geo_area = str(payload.get("geographic_area") or "").strip()
    selected_areas = payload.get("selected_areas") or parse_geographic_areas(geo_area)
    county_stats = payload.get("county_stats") or {}
    is_multi_county = len(selected_areas) > 1 or geo_area == "ALL_ONTARIO"
    items = payload.get("items") or []
    hit_count = len(items)
    monitored_count = int(payload.get("monitored_count") or 0)
    munis_checked = int(payload.get("munis_with_docs_checked") or 0)
    docs_checked = int(payload.get("docs_checked") or 0)
    already_sent = int(payload.get("already_sent_skipped") or 0)
    keywords = payload.get("keywords") or []
    neg_keywords = payload.get("negative_keywords") or []
    monitored_munis = payload.get("monitored_municipalities") or []
    run_date_str = datetime.date.today().strftime("%B %d, %Y")

    area_label = format_areas_human(selected_areas if selected_areas else geo_area)

    if hit_count == 0:
        subject = f"OFA Municipal Council Watch — {fed_name}: All Clear (0 New Matches | {run_date_str})"
    else:
        s_word = "Match" if hit_count == 1 else "Matches"
        subject = f"OFA Municipal Council Watch — {fed_name}: {hit_count} New {s_word} ({run_date_str})"

    if is_test_banner:
        subject = f"[TEST PREVIEW] {subject}"

    # Logo <img> tag (exact proportions, never stretched)
    logo_html = ""
    logo_bytes = _prepare_trimmed_logo_bytes()
    if logo_bytes:
        if logo_mode == "inline":
            b64 = base64.b64encode(logo_bytes).decode("ascii")
            src = f"data:image/png;base64,{b64}"
        else:
            src = "cid:ofa_logo"
        logo_html = (
            f'<img src="{src}" alt="Ontario Federation of Agriculture" '
            f'width="195" style="display:block; width:195px; height:auto; border:0;" />'
        )
    else:
        logo_html = (
            f'<span style="font-family:Arial,Helvetica,sans-serif; font-size:22px; '
            f'font-weight:bold; color:{OFA_VALENCIA};">OFA</span> '
            f'<span style="font-family:Arial,Helvetica,sans-serif; font-size:13px; '
            f'font-weight:bold; color:{OFA_BLACK};">Ontario Federation of Agriculture</span>'
        )

    test_banner_html = ""
    if is_test_banner:
        test_banner_html = f"""
        <tr>
          <td style="background-color:{OFA_TULIP}; color:{OFA_BLACK}; padding:10px 28px; font-family:Arial,Helvetica,sans-serif; font-size:13px; font-weight:bold;">
            TEST PREVIEW MODE — Sent for review before live County Federation delivery.
          </td>
        </tr>
        """

    # Watchlist pill HTML
    kw_pills = " ".join(
        f'<span style="display:inline-block; background-color:{OFA_CHAMPAGNE}; color:{OFA_BLUEWOOD}; '
        f'font-family:Arial,Helvetica,sans-serif; font-size:12px; font-weight:bold; '
        f'padding:3px 8px; margin:2px 4px 2px 0; border-radius:3px;">{html.escape(k)}</span>'
        for k in keywords
    )
    neg_note = ""
    if neg_keywords:
        neg_note = (
            f'<div style="margin-top:6px; font-size:12px; color:#555555;">'
            f'<strong>Excluded terms:</strong> {html.escape(", ".join(neg_keywords))}</div>'
        )

    # Optional Multi-County Overview Table (when monitoring 2+ counties)
    county_overview_html = ""
    if is_multi_county and county_stats and len(county_stats) <= 15:
        ov_rows = []
        for idx_a, area_name in enumerate(sorted(county_stats.keys())):
            st_c = county_stats[area_name]
            bg = "#FFFFFF" if idx_a % 2 == 0 else "#FAF8F6"
            h_cnt = int(st_c.get("hits_count") or 0)
            r_cnt = int(st_c.get("renewals_count") or 0)
            d_cnt = int(st_c.get("docs_checked") or 0)
            m_cnt = int(st_c.get("monitored_count") or 0)
            h_cell = (
                f'<span style="display:inline-block; background-color:{OFA_VALENCIA}; color:#FFFFFF; font-size:11px; font-weight:bold; padding:2px 8px; border-radius:3px;">{h_cnt}</span>'
                if h_cnt > 0
                else '<span style="color:#666666; font-size:12px;">0 (All Clear)</span>'
            )
            r_cell = (
                f'<strong style="color:{OFA_VALENCIA};">{r_cnt}</strong>'
                if r_cnt > 0
                else '<span style="color:#666666;">0</span>'
            )
            ov_rows.append(
                f'<tr style="background-color:{bg};">'
                f'<td style="padding:7px 10px; border-bottom:1px solid #E5E8EC; font-size:12px; font-weight:bold; color:{OFA_BLUEWOOD};">{html.escape(area_name)}</td>'
                f'<td align="center" style="padding:7px 8px; border-bottom:1px solid #E5E8EC;">{h_cell}</td>'
                f'<td align="center" style="padding:7px 8px; border-bottom:1px solid #E5E8EC; font-size:12px; color:#333333;">{d_cnt} ({m_cnt} munis)</td>'
                f'<td align="center" style="padding:7px 8px; border-bottom:1px solid #E5E8EC; font-size:12px;">{r_cell}</td>'
                f'</tr>'
            )
        county_overview_html = f"""
        <tr>
          <td style="padding:8px 28px 12px 28px; font-family:Arial,Helvetica,sans-serif;">
            <div style="font-size:12px; font-weight:bold; color:{OFA_BLUEWOOD}; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:6px;">
              At-a-Glance Breakdown by County / Region
            </div>
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse; border:1px solid #DCE1E6;">
              <tr style="background-color:{OFA_BLUEWOOD}; color:#FFFFFF;">
                <th align="left" style="padding:7px 10px; font-size:11px; text-transform:uppercase;">County / Region</th>
                <th align="center" style="padding:7px 8px; font-size:11px; text-transform:uppercase;">Council Matches</th>
                <th align="center" style="padding:7px 8px; font-size:11px; text-transform:uppercase;">Docs Checked</th>
                <th align="center" style="padding:7px 8px; font-size:11px; text-transform:uppercase;">12-Mo Renewals</th>
              </tr>
              {"".join(ov_rows)}
            </table>
          </td>
        </tr>
        """

    def _render_item_card(idx_num: int, it: dict[str, Any]) -> str:
        badge = str(it.get("status_badge") or "Council Discussion")
        badge_bg, badge_fg = _badge_colors(badge)
        muni_name = html.escape(str(it.get("municipality_name") or "Unknown"))
        headline = html.escape(str(it.get("headline") or muni_name))
        doc_type = html.escape(str(it.get("doc_type") or "Council Document"))
        meet_date = html.escape(str(it.get("meeting_date_display") or ""))
        exec_summary = html.escape(str(it.get("executive_summary") or ""))
        key_action = str(it.get("key_action_or_date") or "").strip()
        doc_url = html.escape(str(it.get("doc_url") or "#"), quote=True)
        item_kws = it.get("matched_keywords") or []
        item_kw_html = " ".join(
            f'<span style="display:inline-block; background-color:#FDECEC; color:{OFA_CRIMSON}; '
            f'border:1px solid #F5C2C2; font-size:11px; font-weight:bold; padding:2px 7px; '
            f'margin-right:4px; border-radius:3px;">{html.escape(k)}</span>'
            for k in item_kws
        )
        full_ctx_html = _highlight_keywords_html(str(it.get("full_context") or ""), item_kws)

        action_box = ""
        if key_action:
            action_box = (
                f'<div style="margin:10px 0 12px 0; padding:8px 12px; background-color:#FFF8EB; '
                f'border-left:3px solid {OFA_TULIP}; font-size:13px; color:#222222;">'
                f'<strong>Key Date / Outcome:</strong> {html.escape(key_action)}</div>'
            )

        return f"""
        <tr>
          <td style="padding:8px 28px 14px 28px; font-family:Arial,Helvetica,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #DCE1E6; border-top:4px solid {OFA_VALENCIA}; border-radius:4px; background-color:#FFFFFF;">
              <tr>
                <td style="padding:18px 20px;">
                  <!-- Municipality & Status Badge -->
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="font-size:12px; font-weight:bold; color:{OFA_BLUEWOOD}; text-transform:uppercase; letter-spacing:0.5px;">
                        {idx_num}. {muni_name} &nbsp;|&nbsp; {meet_date}
                      </td>
                      <td align="right">
                        <span style="display:inline-block; background-color:{badge_bg}; color:{badge_fg}; font-size:11px; font-weight:bold; padding:4px 9px; border-radius:3px;">
                          {html.escape(badge)}
                        </span>
                      </td>
                    </tr>
                  </table>

                  <!-- Headline -->
                  <h2 style="margin:8px 0 6px 0; font-family:Arial,Helvetica,sans-serif; font-size:18px; line-height:1.3; color:{OFA_BLACK};">
                    {headline}
                  </h2>

                  <!-- Document Type & Matched Keywords -->
                  <div style="margin:0 0 12px 0; font-size:12px; color:#555555;">
                    <strong>Source Type:</strong> {doc_type} &nbsp;&bull;&nbsp; <strong>Matched Keywords:</strong> {item_kw_html}
                  </div>

                  <!-- Executive Summary -->
                  <div style="margin:0 0 10px 0; font-size:14px; line-height:1.55; color:#1F2428;">
                    <strong style="color:{OFA_BLUEWOOD};">Summary:</strong> {exec_summary}
                  </div>

                  {action_box}

                  <!-- Full Verbatim Council Discussion Context (OFA Champagne Box) -->
                  <div style="margin-top:14px; background-color:{OFA_CHAMPAGNE}; border-left:4px solid {OFA_BLUEWOOD}; padding:14px 16px; border-radius:3px;">
                    <div style="font-size:12px; font-weight:bold; color:{OFA_BLUEWOOD}; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:8px;">
                      Full Context from Official Municipal Document
                    </div>
                    <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; color:#222222;">
                      {full_ctx_html}
                    </div>
                  </div>

                  <!-- Source Link Button -->
                  <table cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;">
                    <tr>
                      <td style="background-color:{OFA_VALENCIA}; border-radius:4px;">
                        <a href="{doc_url}" target="_blank" style="display:inline-block; padding:10px 18px; font-family:Arial,Helvetica,sans-serif; font-size:13px; font-weight:bold; color:#FFFFFF; text-decoration:none;">
                          View Official Municipal Document &rarr;
                        </a>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    # Body sections: either Quiet Week ("All Clear") or Detailed Discussion Cards (divided by county if multi-county)
    if hit_count == 0:
        prev_note = (
            f" ({already_sent} earlier item{'s' if already_sent != 1 else ''} already reported in a prior digest were not repeated.)"
            if already_sent > 0
            else ""
        )
        muni_list_preview = ", ".join(monitored_munis[:25])
        if len(monitored_munis) > 25:
            muni_list_preview += f" (+{len(monitored_munis) - 25} more)"

        body_sections_html = county_overview_html + f"""
        <tr>
          <td style="padding:16px 28px 16px 28px; font-family:Arial,Helvetica,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{OFA_CHAMPAGNE}; border-left:5px solid {OFA_BLUEWOOD}; border-radius:4px;">
              <tr>
                <td style="padding:20px 22px;">
                  <div style="font-size:18px; font-weight:bold; color:{OFA_BLUEWOOD}; margin-bottom:8px;">
                    All Clear — 0 New Keyword Matches This Week
                  </div>
                  <p style="margin:0 0 10px 0; font-size:14px; line-height:1.55; color:#222222;">
                    OFA's Municipal Intelligence Scanner completed its weekly check for <strong>{html.escape(fed_name)}</strong>
                    and reviewed <strong>{docs_checked} recent council agenda/minutes document{'s' if docs_checked != 1 else ''}</strong>
                    across <strong>{munis_checked} of {monitored_count} monitored municipalities</strong> in {html.escape(area_label)}.
                    No new mentions of your watched keywords were detected this week.{html.escape(prev_note)}
                  </p>
                  <p style="margin:0; font-size:13px; color:#444444;">
                    <strong>Monitored municipalities ({monitored_count}):</strong> {html.escape(muni_list_preview or 'None selected')}
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """
    elif is_multi_county:
        # Clearly divide council matches into County/Region sections
        items_by_area: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            a = str(it.get("geographic_area") or "Other").strip()
            items_by_area.setdefault(a, []).append(it)

        sections = [county_overview_html]
        areas_with_hits = sorted(items_by_area.keys())
        quiet_areas = [a for a in sorted(selected_areas) if a not in items_by_area]

        for area_name in areas_with_hits:
            area_items = items_by_area[area_name]
            n_hits = len(area_items)
            st_c = county_stats.get(area_name, {})
            d_cnt = int(st_c.get("docs_checked") or 0)
            m_cnt = int(st_c.get("monitored_count") or 0)
            sections.append(f"""
            <tr>
              <td style="padding:18px 28px 6px 28px; font-family:Arial,Helvetica,sans-serif;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{OFA_BLUEWOOD}; border-left:6px solid {OFA_VALENCIA}; border-radius:4px;">
                  <tr>
                    <td style="padding:11px 16px; color:#FFFFFF; font-size:15px; font-weight:bold; letter-spacing:0.3px;">
                      {html.escape(area_name.upper())} &mdash; {n_hits} New {'Match' if n_hits == 1 else 'Matches'}
                    </td>
                    <td align="right" style="padding:11px 16px; color:#E0E6EB; font-size:12px;">
                      {d_cnt} docs checked ({m_cnt} munis)
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """)
            for local_idx, it in enumerate(area_items, 1):
                sections.append(_render_item_card(local_idx, it))

        if quiet_areas and len(selected_areas) <= 15:
            quiet_details = []
            for qa in quiet_areas:
                d_cnt = int((county_stats.get(qa) or {}).get("docs_checked") or 0)
                quiet_details.append(f"<strong>{html.escape(qa)}</strong> ({d_cnt} docs checked)")
            sections.append(f"""
            <tr>
              <td style="padding:10px 28px 12px 28px; font-family:Arial,Helvetica,sans-serif;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{OFA_CHAMPAGNE}; border-left:4px solid {OFA_BLUEWOOD}; border-radius:4px;">
                  <tr>
                    <td style="padding:12px 16px; font-size:13px; color:#222222; line-height:1.5;">
                      <strong style="color:{OFA_BLUEWOOD};">All Clear (0 New Matches This Week):</strong>
                      {" &nbsp;&bull;&nbsp; ".join(quiet_details)}
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """)

        body_sections_html = "".join(sections)
    else:
        # Single-county layout with optional quick summary index when >= 2 hits
        toc_html = ""
        if hit_count >= 2:
            toc_rows = []
            for idx, it in enumerate(items, 1):
                toc_rows.append(
                    f'<li style="margin:0 0 6px 0; font-size:13px; color:#222222;">'
                    f'<strong>{html.escape(it["municipality_name"])}</strong> — '
                    f'{html.escape(it.get("headline") or ", ".join(it.get("matched_keywords") or []))} '
                    f'<span style="color:#666666;">({html.escape(it.get("meeting_date_display") or "")})</span></li>'
                )
            toc_html = f"""
            <tr>
              <td style="padding:6px 28px 10px 28px; font-family:Arial,Helvetica,sans-serif;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8F9FA; border:1px solid #E2E6EA; border-radius:4px;">
                  <tr>
                    <td style="padding:14px 18px;">
                      <div style="font-size:13px; font-weight:bold; color:{OFA_BLUEWOOD}; text-transform:uppercase; letter-spacing:0.4px; margin-bottom:8px;">
                        In This Week's Digest
                      </div>
                      <ol style="margin:0; padding-left:20px;">{"".join(toc_rows)}</ol>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """

        cards_html = [_render_item_card(idx, it) for idx, it in enumerate(items, 1)]
        body_sections_html = toc_html + "".join(cards_html)

    # ── Upcoming Bylaw Renewals Section (Next 12 Months) — Always rendered at the bottom ──
    renewals = payload.get("upcoming_renewals") or []
    renewal_months = int(payload.get("renewal_months") or 12)
    renewal_count = len(renewals)

    def _exemption_pill_html(status_val: str) -> str:
        s_low = str(status_val or "").strip().lower()
        s_esc = html.escape(str(status_val or "Not Known"))
        if s_low == "yes":
            return (
                f'<span style="display:inline-block; background-color:#E6F4EA; color:#1B5E20; '
                f'border:1px solid #B7DFC2; font-size:11px; font-weight:bold; padding:2px 8px; '
                f'border-radius:3px; white-space:nowrap;">Yes</span>'
            )
        if s_low in ("no", "no explicit exemption found"):
            return (
                f'<span style="display:inline-block; background-color:{OFA_VALENCIA}; color:#FFFFFF; '
                f'font-size:11px; font-weight:bold; padding:2px 8px; border-radius:3px; white-space:nowrap;">{s_esc}</span>'
            )
        return (
            f'<span style="display:inline-block; background-color:{OFA_CHAMPAGNE}; color:{OFA_BLUEWOOD}; '
            f'font-size:11px; font-weight:bold; padding:2px 8px; border-radius:3px; white-space:nowrap;">{s_esc}</span>'
        )

    def _format_time_left(days_left: int) -> str:
        if days_left <= 0:
            return "Due now"
        if days_left < 45:
            return f"{days_left} days"
        months = max(1, round(days_left / 30.4375))
        return f"~{months} mo" if months == 1 else f"~{months} mos"

    if renewals:
        ren_rows_html = []
        # When monitoring multiple counties, group upcoming renewals clearly by County with Champagne subheaders
        if is_multi_county:
            ordered_renewals = sorted(
                renewals,
                key=lambda x: (str(x.get("geographic_area") or ""), str(x.get("expiry_date") or ""), str(x.get("municipality_name") or "")),
            )
            ren_counts_by_area: dict[str, int] = {}
            for x in ordered_renewals:
                a_k = str(x.get("geographic_area") or "Other")
                ren_counts_by_area[a_k] = ren_counts_by_area.get(a_k, 0) + 1
        else:
            ordered_renewals = renewals
            ren_counts_by_area = {}

        last_ren_area = None
        for r_idx, ren in enumerate(ordered_renewals):
            if is_multi_county:
                cur_area = str(ren.get("geographic_area") or "Other")
                if cur_area != last_ren_area:
                    cnt_a = ren_counts_by_area.get(cur_area, 0)
                    ren_rows_html.append(f"""
                    <tr style="background-color:{OFA_CHAMPAGNE};">
                      <td colspan="5" style="padding:7px 10px; border-top:2px solid {OFA_BLUEWOOD}; border-bottom:1px solid #D5CEC6; font-size:12px; font-weight:bold; color:{OFA_BLUEWOOD}; text-transform:uppercase; letter-spacing:0.4px;">
                        {html.escape(cur_area)} &mdash; {cnt_a} Upcoming {'Renewal' if cnt_a == 1 else 'Renewals'}
                      </td>
                    </tr>
                    """)
                    last_ren_area = cur_area

            row_bg = "#FFFFFF" if r_idx % 2 == 0 else "#FAF8F6"
            m_name = html.escape(str(ren.get("municipality_name") or ""))
            m_tier = html.escape(str(ren.get("municipal_status") or ""))
            c_lbl = html.escape(str(ren.get("category_label") or ""))
            b_name = html.escape(str(ren.get("bylaw_name") or ""))
            b_link = str(ren.get("bylaw_link") or "").strip()
            if b_link and b_link.startswith(("http://", "https://")):
                b_cell = (
                    f'<a href="{html.escape(b_link, quote=True)}" target="_blank" '
                    f'style="color:{OFA_CRIMSON}; text-decoration:underline; font-weight:bold;">{b_name}</a>'
                )
            else:
                b_cell = f'<strong>{b_name}</strong>'

            exp_disp = html.escape(str(ren.get("expiry_date_display") or ren.get("expiry_date") or ""))
            days_left = int(ren.get("days_until_expiry") or 0)
            time_left_str = _format_time_left(days_left)
            ex_pill = _exemption_pill_html(str(ren.get("exemption_status") or "Not Known"))

            ren_rows_html.append(f"""
            <tr style="background-color:{row_bg};">
              <td style="padding:9px 8px; border-bottom:1px solid #E5E8EC; font-size:12px; color:#222222; vertical-align:top;">
                <strong>{m_name}</strong><br />
                <span style="font-size:11px; color:#666666;">{m_tier}</span>
              </td>
              <td style="padding:9px 8px; border-bottom:1px solid #E5E8EC; font-size:12px; color:{OFA_BLUEWOOD}; font-weight:bold; vertical-align:top;">
                {c_lbl}
              </td>
              <td style="padding:9px 8px; border-bottom:1px solid #E5E8EC; font-size:12px; color:#222222; vertical-align:top;">
                {b_cell}
              </td>
              <td style="padding:9px 8px; border-bottom:1px solid #E5E8EC; font-size:12px; color:#222222; white-space:nowrap; vertical-align:top;">
                <strong>{exp_disp}</strong><br />
                <span style="font-size:11px; color:#666666;">({time_left_str})</span>
              </td>
              <td align="center" style="padding:9px 8px; border-bottom:1px solid #E5E8EC; vertical-align:top;">
                {ex_pill}
              </td>
            </tr>
            """)

        renewals_section_html = f"""
        <tr>
          <td style="padding:14px 28px 10px 28px; font-family:Arial,Helvetica,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #DCE1E6; border-top:4px solid {OFA_TULIP}; border-radius:4px; background-color:#FFFFFF;">
              <tr>
                <td style="padding:16px 18px 12px 18px; background-color:#FFFFFF;">
                  <div style="font-size:11px; font-weight:bold; color:{OFA_VALENCIA}; text-transform:uppercase; letter-spacing:0.6px;">
                    OFA Municipal Bylaw Database — Renewal Watch
                  </div>
                  <h2 style="margin:4px 0 6px 0; font-family:Arial,Helvetica,sans-serif; font-size:17px; color:{OFA_BLUEWOOD};">
                    Upcoming Bylaw Renewals in {html.escape(area_label)} (Next {renewal_months} Months)
                  </h2>
                  <p style="margin:0 0 12px 0; font-size:12px; line-height:1.45; color:#555555;">
                    The following <strong>{renewal_count}</strong> municipal bylaw{'s' if renewal_count != 1 else ''}
                    (County/Upper-Tier and Lower/Single-Tier) in your monitored area {'are' if renewal_count != 1 else 'is'}
                    recorded in OFA's Bylaw Database as expiring within the next {renewal_months} months.
                    Municipalities typically begin background studies and public consultations 6–12 months before expiry.
                  </p>

                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse; border:1px solid #DCE1E6;">
                    <tr style="background-color:{OFA_BLUEWOOD}; color:#FFFFFF;">
                      <th align="left" style="padding:8px 8px; font-size:11px; text-transform:uppercase; letter-spacing:0.3px;">Municipality</th>
                      <th align="left" style="padding:8px 8px; font-size:11px; text-transform:uppercase; letter-spacing:0.3px;">Bylaw Category</th>
                      <th align="left" style="padding:8px 8px; font-size:11px; text-transform:uppercase; letter-spacing:0.3px;">Bylaw Name / #</th>
                      <th align="left" style="padding:8px 8px; font-size:11px; text-transform:uppercase; letter-spacing:0.3px;">Expiry Date</th>
                      <th align="center" style="padding:8px 8px; font-size:11px; text-transform:uppercase; letter-spacing:0.3px;">Farm Exemption</th>
                    </tr>
                    {"".join(ren_rows_html)}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """
    else:
        renewals_section_html = f"""
        <tr>
          <td style="padding:10px 28px 10px 28px; font-family:Arial,Helvetica,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F8F9FA; border:1px solid #E2E6EA; border-left:4px solid {OFA_TULIP}; border-radius:4px;">
              <tr>
                <td style="padding:14px 16px;">
                  <div style="font-size:13px; font-weight:bold; color:{OFA_BLUEWOOD}; margin-bottom:4px;">
                    Upcoming Bylaw Renewals (Next {renewal_months} Months): 0 Recorded
                  </div>
                  <div style="font-size:12px; color:#555555; line-height:1.45;">
                    No County or Lower/Single-Tier bylaws in your monitored {html.escape(area_label)} scope are currently
                    recorded in the OFA Bylaw Database as expiring within the next {renewal_months} months.
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """

    # Full OFA-Branded Outlook-Safe Email Template
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(subject)}</title>
</head>
<body style="margin:0; padding:0; background-color:#F2F3F5; font-family:Arial,Helvetica,sans-serif; color:#222222;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F2F3F5; padding:20px 10px;">
    <tr>
      <td align="center">
        <table width="680" cellpadding="0" cellspacing="0" border="0" style="max-width:680px; width:100%; background-color:#FFFFFF; border:1px solid #DDE1E6;">
          <!-- Top Brand Accent Bar -->
          <tr>
            <td style="background-color:{OFA_VALENCIA}; height:6px; font-size:0; line-height:0;">&nbsp;</td>
          </tr>

          {test_banner_html}

          <!-- White Logo Header with Brand Clear Space -->
          <tr>
            <td style="background-color:#FFFFFF; padding:22px 28px 14px 28px; border-bottom:1px solid #EAECEF;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="middle">{logo_html}</td>
                  <td align="right" valign="middle" style="font-family:Arial,Helvetica,sans-serif;">
                    <div style="font-size:11px; font-weight:bold; color:{OFA_VALENCIA}; text-transform:uppercase; letter-spacing:0.8px;">
                      Weekly Municipal Council Watch
                    </div>
                    <div style="font-size:13px; color:{OFA_BLUEWOOD}; font-weight:bold; margin-top:3px;">
                      {html.escape(run_date_str)}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Federation Title & Coverage KPI Bar -->
          <tr>
            <td style="padding:20px 28px 12px 28px; font-family:Arial,Helvetica,sans-serif;">
              <h1 style="margin:0 0 6px 0; font-family:Arial,Helvetica,sans-serif; font-size:22px; font-weight:bold; color:{OFA_BLACK};">
                {html.escape(fed_name)}
              </h1>
              <div style="font-size:13px; color:#555555; margin-bottom:14px;">
                Automated weekly summary of municipal council agendas and minutes across <strong>{html.escape(area_label)}</strong>.
              </div>

              <!-- 4-Column KPI Summary Strip -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate; border-spacing:6px 0; margin:0 -6px;">
                <tr>
                  <td width="25%" align="center" style="background-color:{OFA_BLUEWOOD}; color:#FFFFFF; padding:12px 6px; border-radius:4px;">
                    <div style="font-size:21px; font-weight:bold;">{hit_count}</div>
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.4px; margin-top:2px;">New Matches</div>
                  </td>
                  <td width="25%" align="center" style="background-color:{OFA_CHAMPAGNE}; color:{OFA_BLUEWOOD}; padding:12px 6px; border-radius:4px;">
                    <div style="font-size:21px; font-weight:bold;">{monitored_count}</div>
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.4px; margin-top:2px;">Munis Watched</div>
                  </td>
                  <td width="25%" align="center" style="background-color:{OFA_CHAMPAGNE}; color:{OFA_BLUEWOOD}; padding:12px 6px; border-radius:4px;">
                    <div style="font-size:21px; font-weight:bold;">{docs_checked}</div>
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.4px; margin-top:2px;">Docs Checked</div>
                  </td>
                  <td width="25%" align="center" style="background-color:{'#FFF4E0' if renewal_count > 0 else OFA_CHAMPAGNE}; color:{OFA_BLUEWOOD}; padding:12px 6px; border-radius:4px;">
                    <div style="font-size:21px; font-weight:bold; color:{OFA_VALENCIA if renewal_count > 0 else OFA_BLUEWOOD};">{renewal_count}</div>
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:0.4px; margin-top:2px;">12-Mo Renewals</div>
                  </td>
                </tr>
              </table>

              <!-- Active Keyword Watchlist -->
              <div style="margin-top:14px; font-size:12px; color:#444444;">
                <div style="font-weight:bold; color:{OFA_BLUEWOOD}; margin-bottom:4px;">Active Keyword Watchlist:</div>
                {kw_pills or '<em>No keywords configured</em>'}
                {neg_note}
              </div>
            </td>
          </tr>

          <!-- Main Content (Items or All Clear Card) -->
          {body_sections_html}

          <!-- Upcoming 12-Month Bylaw Renewals (County & Lower/Single Tier) -->
          {renewals_section_html}

          <!-- Methodology / Scope Footnote -->
          <tr>
            <td style="padding:12px 28px 20px 28px; font-family:Arial,Helvetica,sans-serif; font-size:12px; line-height:1.5; color:#666666;">
              <em>Note: Summaries are generated directly from the official municipal agenda/minutes excerpt shown above.
              Always click "View Official Municipal Document" to verify full staff reports, maps, and meeting times before submitting a delegation.</em>
            </td>
          </tr>

          <!-- OFA CTA Bar (Valencia Red left + Black right, strictly paired with Contact Bar below) -->
          <tr>
            <td>
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{OFA_BLACK};">
                <tr>
                  <td width="64%" style="background-color:{OFA_VALENCIA}; padding:14px 20px 14px 28px; font-family:Arial,Helvetica,sans-serif; font-size:13px; font-weight:bold; color:#FFFFFF; border-top-right-radius:26px; border-bottom-right-radius:26px;">
                    Want to add or adjust your county keywords? Email
                    <a href="mailto:ben.lefort@ofa.on.ca" style="color:#FFFFFF; text-decoration:underline;">ben.lefort@ofa.on.ca</a>
                  </td>
                  <td width="36%" align="right" style="background-color:{OFA_BLACK}; padding:14px 28px 14px 16px; font-family:Arial,Helvetica,sans-serif; font-size:12px; font-weight:bold; color:#FFFFFF;">
                    Farms and Food Forever.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- OFA Contact Bar (Clean white background + Brand Quiet Zone, w/o duplicate logo per Guide p.15) -->
          <tr>
            <td align="center" style="background-color:#FFFFFF; padding:18px 28px; font-family:Arial,Helvetica,sans-serif; font-size:12px; color:{OFA_BLACK};">
              <strong><a href="https://ofa.on.ca" style="color:{OFA_BLACK}; text-decoration:none;">ofa.on.ca</a></strong>
              &nbsp;&nbsp;<span style="color:{OFA_VALENCIA}; font-weight:bold;">//</span>&nbsp;&nbsp;
              <strong>Tel:</strong> 519-821-8883 <span style="color:#999999;">/</span> 1-800-668-3276
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, full_html


def send_branded_email(
    subject: str,
    html_body: str,
    to_emails: list[str],
    cc_emails: list[str] | None = None,
    bcc_emails: list[str] | None = None,
    smtp_settings: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Send Outlook-safe HTML email with inline CID OFA logo and true hidden BCC via SMTP envelope."""
    cfg = smtp_settings or load_smtp_settings()
    if not cfg.get("configured"):
        return False, "SMTP credentials not configured in .streamlit/secrets.toml or environment."

    to_clean = _parse_email_list(",".join(to_emails or []))
    cc_clean = _parse_email_list(",".join(cc_emails or []))
    bcc_clean = _parse_email_list(",".join(bcc_emails or []))

    if not to_clean:
        return False, "No valid recipient email addresses provided."

    # Build deduplicated SMTP envelope recipient list (To + Cc + hidden Bcc)
    envelope_rcpts: list[str] = []
    seen_env = set()
    for addr in to_clean + cc_clean + bcc_clean:
        if addr.lower() not in seen_env:
            seen_env.add(addr.lower())
            envelope_rcpts.append(addr)

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"OFA Municipal Intelligence <{cfg['username']}>"
    msg["To"] = ", ".join(to_clean)
    if cc_clean:
        msg["Cc"] = ", ".join(cc_clean)
    # Intentionally DO NOT set msg["Bcc"] header so blind copies remain strictly blind!

    alt = MIMEMultipart("alternative")
    plain_fallback = (
        f"{subject}\n\n"
        "Please view this email in an HTML-compatible email client (such as Outlook) "
        "to read the formatted OFA Weekly Municipal Council Watch digest and source links.\n\n"
        "Ontario Federation of Agriculture | ofa.on.ca | 519-821-8883 / 1-800-668-3276"
    )
    alt.attach(MIMEText(plain_fallback, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    logo_bytes = _prepare_trimmed_logo_bytes()
    if logo_bytes:
        img = MIMEImage(logo_bytes, _subtype="png")
        img.add_header("Content-ID", "<ofa_logo>")
        img.add_header("Content-Disposition", "inline", filename="OFA_logo.png")
        msg.attach(img)

    try:
        with smtplib.SMTP(cfg["server"], int(cfg["port"]), timeout=30) as server:
            server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["username"], envelope_rcpts, msg.as_string())
        return True, f"Sent to {', '.join(to_clean)}" + (f" (BCC: {', '.join(bcc_clean)})" if bcc_clean else "")
    except Exception as exc:
        return False, f"SMTP send failed: {exc}"


def _save_digest_archive(subscription: dict[str, Any], html_inline: str, run_date: str) -> str:
    out_dir = os.path.join(DIGEST_ARCHIVE_DIR, run_date)
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(subscription.get("federation_name") or "county")).strip("_").lower()
    fname = f"{slug}_{subscription.get('id', 'preview')}.html"
    path = os.path.join(out_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_inline)
    return path


def process_subscription(
    conn,
    subscription: dict[str, Any],
    munis_df,
    cached_docs_df,
    *,
    dry_run: bool = False,
    test_to: str | None = None,
    ignore_dedup: bool = False,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Build, archive, and (unless dry_run) send one County Federation's weekly digest."""
    sid = int(subscription["id"])
    fed_name = subscription["federation_name"]
    sent_hashes = set() if ignore_dedup else get_sent_content_hashes(conn, sid)

    payload = build_county_digest_payload(
        subscription=subscription,
        munis_df=munis_df,
        cached_docs_df=cached_docs_df,
        exclude_hashes=sent_hashes,
        use_ai=use_ai,
        conn=conn,
    )

    items = payload["items"]
    run_date = payload["run_date"]
    send_empty = bool(subscription.get("send_empty_digest", True))

    if not items and not send_empty and not test_to:
        return {
            "subscription_id": sid,
            "federation_name": fed_name,
            "status": "skipped_empty",
            "hits": 0,
            "message": "0 new matches and send_empty_digest is disabled.",
        }

    is_test = bool(test_to) or bool(subscription.get("is_test_profile", False))
    subject, html_cid = render_county_digest_html(payload, logo_mode="cid", is_test_banner=bool(test_to))
    _, html_inline = render_county_digest_html(payload, logo_mode="inline", is_test_banner=bool(test_to))
    archive_path = _save_digest_archive(subscription, html_inline, run_date)

    if dry_run:
        return {
            "subscription_id": sid,
            "federation_name": fed_name,
            "status": "dry_run",
            "hits": len(items),
            "archive_path": archive_path,
            "subject": subject,
            "message": f"Dry run saved -> {archive_path}",
        }

    if test_to:
        to_list = _parse_email_list(test_to)
        cc_list = []
        bcc_list = []
        delivery_mode = "test"
    else:
        to_list = _parse_email_list(subscription.get("recipient_emails", ""))
        cc_list = _parse_email_list(subscription.get("cc_emails", ""))
        # Always blind-copy Ben (DEFAULT_BCC_EMAIL) on every automated live run
        bcc_list = _parse_email_list(subscription.get("bcc_emails", "") + f",{DEFAULT_BCC_EMAIL}")
        delivery_mode = "live"

    ok, msg = send_branded_email(
        subject=subject,
        html_body=html_cid,
        to_emails=to_list,
        cc_emails=cc_list,
        bcc_emails=bcc_list,
    )
    if ok:
        record_digest_sent(
            conn=conn,
            subscription_id=sid,
            entries=items,
            run_date=run_date,
            recipients_sent=", ".join(to_list),
            delivery_mode=delivery_mode,
        )

    return {
        "subscription_id": sid,
        "federation_name": fed_name,
        "status": "sent" if ok else "failed",
        "hits": len(items),
        "archive_path": archive_path,
        "subject": subject,
        "message": msg,
        "is_test": is_test,
    }


def run_all_digests(
    *,
    dry_run: bool = False,
    subscription_id: int | None = None,
    test_to: str | None = None,
    ignore_dedup: bool = False,
    use_ai: bool = True,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> list[dict[str, Any]]:
    print("--- STARTING COUNTY FEDERATION WEEKLY DIGEST MAILER ---")
    conn = get_cli_connection(prefer_postgres=True)
    ensure_digest_tables(conn)

    try:
        munis_df = get_municipalities(conn)
        cached_docs_df = load_cached_council_docs(cache_path)
        print(f"Loaded {len(munis_df)} municipalities and {len(cached_docs_df)} cached council documents.")

        if subscription_id is not None:
            sub = get_county_subscription(conn, subscription_id)
            subs = [sub] if sub else []
        else:
            subs = list_county_subscriptions(conn, active_only=True)

        if not subs:
            print("No active County Federation digest subscriptions found. Nothing to send.")
            return []

        results = []
        for sub in subs:
            print(f"  Processing [{sub['id']}] {sub['federation_name']} ({sub['geographic_area']})...")
            res = process_subscription(
                conn=conn,
                subscription=sub,
                munis_df=munis_df,
                cached_docs_df=cached_docs_df,
                dry_run=dry_run,
                test_to=test_to,
                ignore_dedup=ignore_dedup,
                use_ai=use_ai,
            )
            print(f"    -> {res['status'].upper()} | hits={res['hits']} | {res['message']}")
            results.append(res)
        return results
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send or preview OFA County Federation Weekly Council Digests.")
    parser.add_argument("--dry-run", action="store_true", help="Render HTML archives without sending emails")
    parser.add_argument("--subscription-id", type=int, default=None, help="Run only one specific subscription ID")
    parser.add_argument("--test-to", type=str, default=None, help="Send test email only to this address (does not mark live sent log)")
    parser.add_argument("--ignore-dedup", action="store_true", help="Include items already sent in prior weeks (useful for testing)")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic summaries without calling Gemini")
    args = parser.parse_args()

    run_all_digests(
        dry_run=args.dry_run,
        subscription_id=args.subscription_id,
        test_to=args.test_to,
        ignore_dedup=args.ignore_dedup,
        use_ai=not args.no_ai,
    )
