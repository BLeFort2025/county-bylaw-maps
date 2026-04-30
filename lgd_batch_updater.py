"""
lgd_batch_updater.py — Gemini-Powered LGD Bylaw Field Extraction

Downloads the 67 P1 municipalities' bylaw documents, sends each to
Gemini 2.5 Flash for structured LGD field extraction, and produces
a review CSV comparing old DB values vs. AI-extracted values.

Usage:
  set GEMINI_API_KEY=AIza...
  python lgd_batch_updater.py                    # Process all 67 P1 municipalities
  python lgd_batch_updater.py --test 5           # Test mode (first N)
  python lgd_batch_updater.py --audit-csv path   # Use custom audit CSV
"""

import pandas as pd
import requests
import os
import sys
import datetime
import urllib3
import io
import re
import sqlite3
import argparse
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_config import get_region

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from bs4 import BeautifulSoup
    BS4_SUPPORT = True
except ImportError:
    BS4_SUPPORT = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform == "win32":
    # Force unbuffered output so background runs show progress
    os.environ['PYTHONUNBUFFERED'] = '1'

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "bylaws.db")
SIGNALS_DIR = os.path.join(SCRIPT_DIR, "signals")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ── Gemini extraction prompt ──
# NOTE: Uses %%MUNICIPALITY%% and %%COUNTY%% and %%BYLAW_TEXT%% placeholders
# instead of {braces} to avoid conflicts with JSON examples in the prompt.

EXTRACTION_PROMPT_TEMPLATE = """You are a municipal policy analyst for the Ontario Federation of Agriculture.
You are reading the FULL TEXT of a municipal animal control bylaw.

Your task: Extract ALL of the following Livestock Guardian Dog (LGD) data fields from this bylaw.

RULES:
- Return ONLY a valid JSON object with exactly the keys listed below.
- Use "Yes", "No", or "N/A" for yes/no fields.
- Use null if the information is genuinely not found in the bylaw.
- For definition fields, quote the EXACT bylaw text.
- For date_enacted, use YYYY-MM-DD format. If only a year is found, use YYYY-01-01.
- Be thorough — look for LGD provisions anywhere in the document including schedules, appendices, and amendments.
- "Working dog" and "farm dog" are equivalent to livestock guardian dog for our purposes.

Required JSON keys:
{
  "bylaw_name": "The official bylaw name/number exactly as written (e.g. 'BY-LAW NUMBER 2024-045')",
  "date_enacted": "YYYY-MM-DD or null",
  "has_lgd_definition": "Yes/No - does the bylaw define livestock guardian dog, working dog, or farm dog?",
  "lgd_definition": "Full quoted text of the LGD/working dog/farm dog definition, or null",
  "has_herding_def": "Yes/No - does the bylaw define herding dog?",
  "herding_definition": "Full quoted text of the herding dog definition, or null",
  "exempt_license_fees": "Yes/No/N/A - are LGDs/working dogs/farm dogs exempt from dog license fees?",
  "collar_tag_req": "Description of collar and tag requirements for dogs, or null",
  "barking_restrictions": "Yes/No - does the bylaw restrict excessive barking or noise from dogs?",
  "exempt_barking": "Yes/No/N/A - are LGDs/working dogs exempt from barking restrictions?",
  "dog_limit": "The dog limit per property AND any farm/agricultural exemptions to the limit",
  "progress_label": "COMPLETE - FARM FRIENDLY if the bylaw has specific LGD/working dog provisions favourable to farmers, or COMPLETE if it has an animal control bylaw but no farm-friendly LGD provisions",
  "notes": "Any important observations about LGD provisions, amendments, or farm-relevant sections"
}

MUNICIPALITY: %%MUNICIPALITY%% (%%COUNTY%%)

BYLAW TEXT:
---
%%BYLAW_TEXT%%
---

Return ONLY valid JSON. No markdown formatting, no explanation, no code fences."""


def build_extraction_prompt(municipality_name, county, bylaw_text):
    """Build the extraction prompt with safe string replacement (no .format())."""
    return (EXTRACTION_PROMPT_TEMPLATE
            .replace("%%MUNICIPALITY%%", municipality_name)
            .replace("%%COUNTY%%", county)
            .replace("%%BYLAW_TEXT%%", bylaw_text))


# ── Text extraction ──

def extract_text_from_pdf(pdf_bytes):
    if not PDF_SUPPORT:
        return ""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:50]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text


def fetch_and_extract_text(url, timeout=20):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        if response.status_code != 200:
            return "", response.status_code

        content_type = response.headers.get('Content-Type', '').lower()

        if 'pdf' in content_type or url.lower().endswith('.pdf'):
            return extract_text_from_pdf(response.content), 200
        else:
            if BS4_SUPPORT:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                return soup.get_text(separator=" ", strip=True), 200
            return response.text, 200
    except requests.exceptions.Timeout:
        return "", -1
    except Exception:
        return "", -2


# ── Gemini API call with retry ──

def extract_lgd_fields_gemini(model, municipality_name, county, bylaw_text, max_retries=5):
    """Send bylaw text to Gemini and parse the JSON response.

    Returns (parsed_dict, raw_response, error_msg).
    """
    # Truncate very long bylaws to ~60k chars (~15k tokens) to stay within limits
    if len(bylaw_text) > 60000:
        bylaw_text = bylaw_text[:60000] + "\n\n[... TRUNCATED — document exceeds 60,000 characters ...]"

    prompt = build_extraction_prompt(municipality_name, county, bylaw_text)

    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()

            # Clean markdown code fences if present
            if raw.startswith('```'):
                lines = raw.split('\n')
                lines = [l for l in lines if not l.strip().startswith('```')]
                raw = '\n'.join(lines).strip()

            parsed = json.loads(raw)
            return parsed, raw, None

        except json.JSONDecodeError as e:
            if attempt < max_retries:
                time.sleep(5)
                continue
            return None, raw, f"JSON parse error: {e}"

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                # Rate limited — use longer exponential backoff
                wait = 30 + (15 * attempt)  # 30s, 45s, 60s, 75s, 90s
                print(f"      Rate limited (attempt {attempt+1}/{max_retries+1}), waiting {wait}s...")
                time.sleep(wait)
                if attempt < max_retries:
                    continue
            return None, "", f"API error: {error_str[:200]}"

    return None, "", "Max retries exceeded"


# ── Load current DB values for comparison ──

def load_current_db_values():
    """Load all current LGD data from the local SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT m.name, m.geographic_area, m.municipal_status,
               b.id as bylaw_id, b.progress_label, b.bylaw_name, b.bylaw_link,
               b.date_enacted, b.date_last_updated,
               d.has_lgd_definition, d.lgd_definition,
               d.has_herding_def, d.herding_definition,
               d.exempt_license_fees, d.collar_tag_req,
               d.barking_restrictions, d.exempt_barking, d.dog_limit
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'LGD'
        LEFT JOIN details_lgd d ON d.bylaw_id = b.id
        WHERE m.municipal_status != 'Upper Tier'
        ORDER BY m.name
    """).fetchall()

    result = {}
    for r in rows:
        result[r["name"]] = dict(r)
    conn.close()
    return result


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="LGD Batch Updater — Gemini Extraction")
    parser.add_argument("--test", type=int, default=0, help="Test mode: process first N municipalities")
    parser.add_argument("--audit-csv", type=str, default=None, help="Path to audit CSV (default: latest)")
    parser.add_argument("--api-key", type=str, default=None, help="Gemini API key (or set GEMINI_API_KEY env)")
    parser.add_argument("--delay", type=int, default=6, help="Seconds between API calls (default: 6)")
    args = parser.parse_args()

    print("=" * 70)
    print("  LGD BATCH UPDATER — GEMINI EXTRACTION PIPELINE")
    print(f"  Date: {datetime.date.today().isoformat()}")
    print("=" * 70)

    # ── Configure Gemini ──
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: No API key. Set GEMINI_API_KEY env var or use --api-key")
        return
    if not GENAI_AVAILABLE:
        print("ERROR: google-generativeai package not installed")
        return

    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("  Gemini 2.5 Flash configured successfully")

    # ── Load audit CSV ──
    audit_path = args.audit_csv
    if not audit_path:
        # Find the latest audit CSV
        candidates = [f for f in os.listdir(SIGNALS_DIR) if f.startswith("lgd_audit_") and f.endswith(".csv")]
        if not candidates:
            print("ERROR: No audit CSV found in signals/. Run lgd_audit_scanner.py first.")
            return
        candidates.sort(reverse=True)
        audit_path = os.path.join(SIGNALS_DIR, candidates[0])

    print(f"  Loading audit: {audit_path}")
    audit_df = pd.read_csv(audit_path)

    # ── Filter to P1 municipalities ──
    p1 = audit_df[audit_df['Audit Result'].isin(['OUTDATED', 'NEW LGD PROVISIONS'])].copy()
    print(f"  P1 municipalities: {len(p1)} (OUTDATED: {(p1['Audit Result']=='OUTDATED').sum()}, NEW: {(p1['Audit Result']=='NEW LGD PROVISIONS').sum()})")

    if args.test > 0:
        p1 = p1.head(args.test)
        print(f"  TEST MODE: Processing first {len(p1)} only")

    # ── Load current DB values ──
    db_values = load_current_db_values()
    print(f"  Loaded {len(db_values)} DB records for comparison")
    print("-" * 70)

    # ── Process each municipality ──
    results = []
    total = len(p1)
    success_count = 0
    error_count = 0
    start_time = time.time()

    for idx, (_, row) in enumerate(p1.iterrows(), 1):
        muni_name = row['Municipality']
        county = row.get('County', 'Unknown')
        source_url = row.get('Source URL', '')
        audit_result = row.get('Audit Result', '')

        print(f"\n  [{idx}/{total}] {muni_name} ({county}) — {audit_result}")

        # Step 1: Download bylaw text
        print(f"    Downloading bylaw...")
        bylaw_text, status = fetch_and_extract_text(source_url)

        if not bylaw_text or len(bylaw_text.strip()) < 100:
            print(f"    SKIP — could not extract text (status: {status})")
            results.append({
                "Municipality": muni_name,
                "County": county,
                "Audit Result": audit_result,
                "Extraction Status": "FAILED - no text",
                "Source URL": source_url,
                "Error": f"HTTP {status}, text length: {len(bylaw_text)}",
            })
            error_count += 1
            continue

        text_len = len(bylaw_text)
        print(f"    Extracted {text_len:,} chars")

        # Step 2: Send to Gemini
        print(f"    Sending to Gemini 2.5 Flash...")
        parsed, raw_response, error = extract_lgd_fields_gemini(model, muni_name, county, bylaw_text)

        if error:
            print(f"    ERROR: {error}")
            results.append({
                "Municipality": muni_name,
                "County": county,
                "Audit Result": audit_result,
                "Extraction Status": "FAILED - AI error",
                "Source URL": source_url,
                "Error": error,
            })
            error_count += 1
        else:
            print(f"    SUCCESS — extracted {sum(1 for v in parsed.values() if v is not None)} fields")
            success_count += 1

            # Build result row with old vs new comparison
            db_rec = db_values.get(muni_name, {})
            result_row = {
                "Municipality": muni_name,
                "County": county,
                "Tier": row.get('Tier', ''),
                "Region": row.get('Region', ''),
                "Audit Result": audit_result,
                "Extraction Status": "SUCCESS",
                "Source URL": source_url,
                # New values from Gemini
                "NEW_bylaw_name": parsed.get("bylaw_name", ""),
                "NEW_date_enacted": parsed.get("date_enacted", ""),
                "NEW_progress_label": parsed.get("progress_label", ""),
                "NEW_has_lgd_definition": parsed.get("has_lgd_definition", ""),
                "NEW_lgd_definition": parsed.get("lgd_definition", ""),
                "NEW_has_herding_def": parsed.get("has_herding_def", ""),
                "NEW_herding_definition": parsed.get("herding_definition", ""),
                "NEW_exempt_license_fees": parsed.get("exempt_license_fees", ""),
                "NEW_collar_tag_req": parsed.get("collar_tag_req", ""),
                "NEW_barking_restrictions": parsed.get("barking_restrictions", ""),
                "NEW_exempt_barking": parsed.get("exempt_barking", ""),
                "NEW_dog_limit": parsed.get("dog_limit", ""),
                "NEW_notes": parsed.get("notes", ""),
                # Old values from DB
                "OLD_bylaw_name": db_rec.get("bylaw_name", ""),
                "OLD_date_enacted": db_rec.get("date_enacted", ""),
                "OLD_progress_label": db_rec.get("progress_label", ""),
                "OLD_has_lgd_definition": db_rec.get("has_lgd_definition", ""),
                "OLD_lgd_definition": db_rec.get("lgd_definition", ""),
                "OLD_has_herding_def": db_rec.get("has_herding_def", ""),
                "OLD_herding_definition": db_rec.get("herding_definition", ""),
                "OLD_exempt_license_fees": db_rec.get("exempt_license_fees", ""),
                "OLD_collar_tag_req": db_rec.get("collar_tag_req", ""),
                "OLD_barking_restrictions": db_rec.get("barking_restrictions", ""),
                "OLD_exempt_barking": db_rec.get("exempt_barking", ""),
                "OLD_dog_limit": db_rec.get("dog_limit", ""),
                # DB record ID for updates
                "DB_bylaw_id": db_rec.get("bylaw_id", ""),
            }
            results.append(result_row)

        # Rate limit delay
        if idx < total:
            print(f"    Waiting {args.delay}s (rate limit)...")
            time.sleep(args.delay)

    # ── Summary ──
    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print("  EXTRACTION COMPLETE")
    print(f"  Processed: {total} municipalities in {elapsed:.0f}s")
    print(f"  Success:   {success_count}")
    print(f"  Failed:    {error_count}")
    print("=" * 70)

    # ── Save review CSV ──
    output_file = os.path.join(SIGNALS_DIR, f"lgd_extraction_review_{datetime.date.today().isoformat()}.csv")
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n  Review CSV saved to: {output_file}")
    print("  Open in Excel, review the NEW_ vs OLD_ columns, then run lgd_apply_updates.py")


if __name__ == "__main__":
    main()
