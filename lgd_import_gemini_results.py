"""
lgd_import_gemini_results.py — Import Gemini Chat Extraction Results

Takes the JSON output from Gemini Pro chat sessions and converts it
into the review CSV format that lgd_apply_updates.py expects.

Usage:
  python lgd_import_gemini_results.py                    # Interactive: paste JSON
  python lgd_import_gemini_results.py --file results.json  # From file
  python lgd_import_gemini_results.py --dir signals/       # Merge all batch_results_*.json files
"""

import pandas as pd
import os
import sys
import sqlite3
import json
import datetime
import argparse
import glob

if sys.platform == "win32":
    os.environ['PYTHONUNBUFFERED'] = '1'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "bylaws.db")
SIGNALS_DIR = os.path.join(SCRIPT_DIR, "signals")


def load_db_values():
    """Load current LGD data from SQLite for comparison."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT m.name, m.geographic_area,
               b.id as bylaw_id, b.progress_label, b.bylaw_name, b.bylaw_link,
               b.date_enacted,
               d.has_lgd_definition, d.lgd_definition,
               d.has_herding_def, d.herding_definition,
               d.exempt_license_fees, d.collar_tag_req,
               d.barking_restrictions, d.exempt_barking, d.dog_limit
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'LGD'
        LEFT JOIN details_lgd d ON d.bylaw_id = b.id
        ORDER BY m.name
    """).fetchall()
    result = {}
    for r in rows:
        result[r["name"]] = dict(r)
    conn.close()
    return result


def parse_gemini_json(text):
    """Parse JSON from Gemini's response, handling markdown code fences."""
    text = text.strip()
    
    # Remove markdown code fences
    if text.startswith('```'):
        lines = text.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        text = '\n'.join(lines).strip()
    
    return json.loads(text)


def build_review_rows(gemini_results, db_values):
    """Convert Gemini extraction results into review CSV rows."""
    rows = []
    for item in gemini_results:
        muni_name = item.get("municipality", "")
        db_rec = db_values.get(muni_name, {})
        
        row = {
            "Municipality": muni_name,
            "County": item.get("county", ""),
            "Extraction Status": "SUCCESS",
            "Source URL": "",
            # New values from Gemini
            "NEW_bylaw_name": item.get("bylaw_name", ""),
            "NEW_date_enacted": item.get("date_enacted", ""),
            "NEW_progress_label": item.get("progress_label", ""),
            "NEW_has_lgd_definition": item.get("has_lgd_definition", ""),
            "NEW_lgd_definition": item.get("lgd_definition", ""),
            "NEW_has_herding_def": item.get("has_herding_def", ""),
            "NEW_herding_definition": item.get("herding_definition", ""),
            "NEW_exempt_license_fees": item.get("exempt_license_fees", ""),
            "NEW_collar_tag_req": item.get("collar_tag_req", ""),
            "NEW_barking_restrictions": item.get("barking_restrictions", ""),
            "NEW_exempt_barking": item.get("exempt_barking", ""),
            "NEW_dog_limit": item.get("dog_limit", ""),
            "NEW_notes": item.get("notes", ""),
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
            "DB_bylaw_id": db_rec.get("bylaw_id", ""),
        }
        rows.append(row)
    
    return rows


def main():
    parser = argparse.ArgumentParser(description="Import Gemini LGD Extraction Results")
    parser.add_argument("--file", type=str, help="Path to a JSON file with Gemini results")
    parser.add_argument("--dir", type=str, help="Directory containing batch_results_*.json files")
    args = parser.parse_args()

    print("=" * 60)
    print("  IMPORT GEMINI LGD EXTRACTION RESULTS")
    print("=" * 60)

    db_values = load_db_values()
    print(f"  Loaded {len(db_values)} DB records for comparison")

    all_results = {}

    if args.file:
        # Load from a single file
        with open(args.file, 'r', encoding='utf-8') as f:
            data = parse_gemini_json(f.read())
        for item in data:
            all_results[item.get("municipality", "")] = item
        print(f"  Loaded {len(data)} municipalities from {args.file}")

    elif args.dir:
        # Merge all batch result files
        pattern = os.path.join(args.dir, "gemini_batch_results_*.json")
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"  No files matching {pattern}")
            print("  Save Gemini's JSON output as gemini_batch_results_1.json, _2.json, etc.")
            return
        for f_path in files:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = parse_gemini_json(f.read())
            for item in data:
                all_results[item.get("municipality", "")] = item
            print(f"  Loaded {len(data)} municipalities from {os.path.basename(f_path)}")

    else:
        # Interactive: paste JSON
        print("\n  Paste the JSON array from Gemini below.")
        print("  When done, type END on a new line and press Enter.\n")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except EOFError:
                break
        
        text = '\n'.join(lines)
        data = parse_gemini_json(text)
        for item in data:
            all_results[item.get("municipality", "")] = item
        print(f"\n  Parsed {len(data)} municipalities from pasted JSON")

    if not all_results:
        print("  No results to process.")
        return

    # Build review rows
    rows = build_review_rows(list(all_results.values()), db_values)
    
    # Save
    output_file = os.path.join(SIGNALS_DIR, f"lgd_extraction_review_{datetime.date.today().isoformat()}.csv")
    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print(f"\n  Saved {len(rows)} rows to: {output_file}")
    print(f"  Next: review in Excel, then run lgd_apply_updates.py")

    # Quick summary
    farm_friendly = sum(1 for r in rows if r.get("NEW_progress_label") == "COMPLETE - FARM FRIENDLY")
    complete = sum(1 for r in rows if r.get("NEW_progress_label") == "COMPLETE")
    print(f"\n  Summary:")
    print(f"    COMPLETE - FARM FRIENDLY: {farm_friendly}")
    print(f"    COMPLETE (no LGD provisions): {complete}")
    print(f"    Total: {len(rows)}")
    print(f"\n  ℹ️  After applying updates with lgd_apply_updates.py,")
    print(f"      remember to sync to cloud:  python sync_to_cloud.py --push")


if __name__ == "__main__":
    main()
