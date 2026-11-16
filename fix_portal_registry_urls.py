"""
fix_portal_registry_urls.py — Deterministically repair verified portal URLs in signals/portal_registry.csv.
"""

from __future__ import annotations

import os
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

DIRECT_FIXES: dict[str, dict[str, str]] = {
    "ARMSTRONG": {"minutes_listing_url": "https://armstrongtownship.com/"},
    "CENTRE HASTINGS": {
        "minutes_listing_url": "https://centrehastings.civicweb.net/Portal/",
        "agenda_listing_url": "https://centrehastings.civicweb.net/Portal/",
    },
    "EAST FERRIS": {"minutes_listing_url": "https://pub-eastferris.escribemeetings.com/"},
    "FAUQUIER STRICKLAND": {"minutes_listing_url": "https://www.fauquierstrickland.com/en/"},
    "Hastings Highlands": {"minutes_listing_url": "https://hastingshighlands.civicweb.net/Portal/"},
    "HIGHLANDS EAST": {
        "council_listing_url": "https://highlandseast.civicweb.net/Portal/",
        "minutes_listing_url": "https://highlandseast.civicweb.net/Portal/",
        "agenda_listing_url": "https://highlandseast.civicweb.net/Portal/",
    },
    "KINGSTON": {"minutes_listing_url": "https://pub-cityofkingston.escribemeetings.com/"},
    "NORTH STORMONT": {
        "portal_type": "civicweb",
        "council_listing_url": "https://northstormont.civicweb.net/Portal/",
        "minutes_listing_url": "https://northstormont.civicweb.net/Portal/",
        "agenda_listing_url": "https://northstormont.civicweb.net/Portal/",
    },
    "SOUTH STORMONT": {"minutes_listing_url": "https://pub-southstormont.escribemeetings.com/"},
    "ST CHARLES": {
        "portal_type": "escribe",
        "council_listing_url": "https://pub-stcharlesontario.escribemeetings.com/",
        "minutes_listing_url": "https://pub-stcharlesontario.escribemeetings.com/",
        "agenda_listing_url": "https://pub-stcharlesontario.escribemeetings.com/",
    },
    "STIRLING RAWDON": {"minutes_listing_url": "https://stirling-rawdon.civicweb.net/Portal/"},
    "STRONG": {"minutes_listing_url": "https://www.strongtownship.com/en/local-government/agendas-and-minutes.aspx"},
    "WHITCHURCH STOUFFVILLE": {"minutes_listing_url": "https://whitchurch.civicweb.net/Portal/"},
    "WOLLASTON": {"minutes_listing_url": "https://wollaston.civicweb.net/Portal/"},
    "Hastings County": {"minutes_listing_url": "https://hastingscounty.civicweb.net/Portal/"},
    "BRADFORD WEST GWILLIMBURY": {
        "council_listing_url": "https://pub-bradfordwestgwillimbury.escribemeetings.com/",
        "minutes_listing_url": "https://pub-bradfordwestgwillimbury.escribemeetings.com/",
        "agenda_listing_url": "https://pub-bradfordwestgwillimbury.escribemeetings.com/",
    },
    "WEST LINCOLN": {"minutes_listing_url": "https://pub-westlincoln.escribemeetings.com/"},
    "WEST NIPISSING": {
        "portal_type": "escribe",
        "council_listing_url": "https://pub-westnipissingouest.escribemeetings.com/",
        "minutes_listing_url": "https://pub-westnipissingouest.escribemeetings.com/",
        "agenda_listing_url": "https://pub-westnipissingouest.escribemeetings.com/",
    },
    "WEST PERTH": {
        "portal_type": "civicweb",
        "council_listing_url": "https://westperth.civicweb.net/Portal/",
        "minutes_listing_url": "https://westperth.civicweb.net/Portal/",
        "agenda_listing_url": "https://westperth.civicweb.net/Portal/",
    },
    "WESTPORT": {
        "portal_type": "civicweb",
        "council_listing_url": "https://villageofwestport.civicweb.net/Portal/",
        "minutes_listing_url": "https://villageofwestport.civicweb.net/Portal/",
        "agenda_listing_url": "https://villageofwestport.civicweb.net/Portal/",
    },
    "Hamilton, Tp": {
        "portal_type": "civicweb",
        "council_listing_url": "https://hamilton.civicweb.net/Portal/",
        "minutes_listing_url": "https://hamilton.civicweb.net/Portal/",
        "agenda_listing_url": "https://hamilton.civicweb.net/Portal/",
    },
    "OTONABEE SOUTH MONAGHAN": {
        "portal_type": "civicweb",
        "council_listing_url": "https://otonabeesouthmonaghan.civicweb.net/Portal/",
        "minutes_listing_url": "https://otonabeesouthmonaghan.civicweb.net/Portal/",
        "agenda_listing_url": "https://otonabeesouthmonaghan.civicweb.net/Portal/",
    },
    "PRINCE EDWARD": {
        "portal_type": "civicweb",
        "council_listing_url": "https://princeedwardcounty.civicweb.net/Portal/",
        "minutes_listing_url": "https://princeedwardcounty.civicweb.net/Portal/",
        "agenda_listing_url": "https://princeedwardcounty.civicweb.net/Portal/",
    },
    "County of Frontenac": {
        "portal_type": "custom_html_pdf",
        "council_listing_url": "https://frcpublicmeetings.powerappsportals.com/",
        "minutes_listing_url": "https://frcpublicmeetings.powerappsportals.com/",
        "agenda_listing_url": "https://frcpublicmeetings.powerappsportals.com/",
    },
    "PERTH SOUTH": {"minutes_listing_url": "https://perthsouth.civicweb.net/Portal/"},
    "NIAGARA FALLS": {
        "portal_type": "civicweb",
        "council_listing_url": "https://niagarafalls.civicweb.net/Portal/",
        "minutes_listing_url": "https://niagarafalls.civicweb.net/Portal/",
        "agenda_listing_url": "https://niagarafalls.civicweb.net/Portal/",
    },
    "SOUTH BRUCE": {"minutes_listing_url": "https://southbruce.civicweb.net/Portal/"},
    "SOUTH BRUCE PENINSULA": {
        "portal_type": "civicweb",
        "council_listing_url": "https://southbrucepeninsula.civicweb.net/Portal/",
        "minutes_listing_url": "https://southbrucepeninsula.civicweb.net/Portal/",
        "agenda_listing_url": "https://southbrucepeninsula.civicweb.net/Portal/",
    },
    "POINT EDWARD": {
        "council_listing_url": "https://www.villageofpointedward.com/municipal-office/council-meetings",
        "minutes_listing_url": "https://www.villageofpointedward.com/municipal-office/council-meetings",
        "agenda_listing_url": "https://www.villageofpointedward.com/municipal-office/council-meetings",
    },
    "NEWBURY": {
        "council_listing_url": "https://www.newbury.ca/copy-of-2025-council-meeting-minutes",
        "minutes_listing_url": "https://www.newbury.ca/copy-of-2025-council-meeting-minutes",
        "agenda_listing_url": "https://www.newbury.ca/copy-of-2025-council-meeting-minutes",
    },
    "PRINCE": {
        "council_listing_url": "https://www.princetownship.ca/agendas-and-minutes.html",
        "minutes_listing_url": "https://www.princetownship.ca/agendas-and-minutes.html",
        "agenda_listing_url": "https://www.princetownship.ca/agendas-and-minutes.html",
    },
    "LAURENTIAN HILLS": {"minutes_listing_url": "https://www.laurentianhills.ca/council/minutes-agendas/"},
    "LAURENTIAN VALLEY": {
        "council_listing_url": "https://www.lvtownship.ca/lv-government-services/council/",
        "minutes_listing_url": "https://www.lvtownship.ca/lv-government-services/council/",
        "agenda_listing_url": "https://www.lvtownship.ca/lv-government-services/council/",
    },
    "BILLINGS": {
        "council_listing_url": "https://www.billingstwp.ca/townhall/agendas-and-minutes/",
        "minutes_listing_url": "https://www.billingstwp.ca/townhall/agendas-and-minutes/",
        "agenda_listing_url": "https://www.billingstwp.ca/townhall/agendas-and-minutes/",
    },
    "CALVIN": {
        "council_listing_url": "https://www.calvintownship.ca/en/council-and-council-business/meetings-agendas",
        "minutes_listing_url": "https://www.calvintownship.ca/en/council-and-council-business/meetings-agendas",
        "agenda_listing_url": "https://www.calvintownship.ca/en/council-and-council-business/meetings-agendas",
    },
    "ADJALA TOSORONTIO": {"council_listing_url": "https://adjala-tosorontio.civicweb.net/Portal/"},
    "BRANT": {"portal_type": "escribe"},
    "SEGUIN": {
        "portal_type": "custom_html_pdf",
        "council_listing_url": "https://www.seguin.ca/council-and-committee-calendar",
        "minutes_listing_url": "https://www.seguin.ca/council-and-committee-calendar",
        "agenda_listing_url": "https://www.seguin.ca/council-and-committee-calendar",
    },
    "TAY VALLEY": {
        "portal_type": "custom_html_pdf",
        "council_listing_url": "https://www.tayvalleytwp.ca/municipal-government/council/council-committee-meetings/",
        "minutes_listing_url": "https://www.tayvalleytwp.ca/municipal-government/council/council-committee-meetings/",
        "agenda_listing_url": "https://www.tayvalleytwp.ca/municipal-government/council/council-committee-meetings/",
    },
    "THORNLOE": {
        "portal_type": "NOT_FOUND",
        "council_listing_url": "",
        "minutes_listing_url": "",
        "agenda_listing_url": "",
    },
}

DEAD_HOSTS_GLOBAL = (
    "stclair.civicweb.net",
    "westgrey.civicweb.net",
    "otonabee.civicweb.net",
    "pub-pec.escribemeetings.com",
    "frontenaccounty.civicweb.net",
    "cityofseguintx.legistar.com",
    "seguintexas.gov",
    "thornloe.ca",
)

JS_TYPES = {"escribe", "(escribe)", "civicweb", "granicus_legistar"}
JS_DOMAINS = ("escribemeetings.com", "civicweb.net", "legistar.com")


def _dns_ok(host: str) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, 443)
        return True
    except Exception:
        return False


def main() -> None:
    df = pd.read_csv(REGISTRY_PATH)
    initial_rows = len(df)
    assert initial_rows == 444, f"Expected 444 rows, got {initial_rows}"

    # 1. Direct verified portal fixes
    direct_updates = 0
    for muni_name, updates in DIRECT_FIXES.items():
        mask = df["municipality_name"] == muni_name
        matched = int(mask.sum())
        if matched != 1:
            raise RuntimeError(f"Expected 1 match for {muni_name}, found {matched}")
        idx = df.index[mask][0]
        for col, val in updates.items():
            if str(df.at[idx, col] if pd.notna(df.at[idx, col]) else "").strip() != val:
                df.at[idx, col] = val
                direct_updates += 1

    # 2. Scrub stale/dead example_recent_minutes_url values
    scrubbed = 0
    for idx, row in df.iterrows():
        ex_url = str(row.get("example_recent_minutes_url", "") or "").strip().lower()
        name = str(row.get("municipality_name", "") or "").strip()
        is_dead = any(h in ex_url for h in DEAD_HOSTS_GLOBAL)
        if name == "PERTH SOUTH" and "pertheast.civicweb.net" in ex_url:
            is_dead = True
        if name == "SOUTH BRUCE" and "southbrucepeninsula.civicweb.net" in ex_url:
            is_dead = True
        if name == "TAY VALLEY" and "tay.civicweb.net" in ex_url:
            is_dead = True
        if is_dead:
            df.at[idx, "example_recent_minutes_url"] = ""
            df.at[idx, "example_recent_minutes_date"] = ""
            scrubbed += 1

    # 3. Promote verified live JS portals from council_listing_url to minutes_listing_url
    promoted = 0
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    for idx, row in df.iterrows():
        pt = str(row.get("portal_type", "") or "").strip().lower()
        if pt not in JS_TYPES:
            continue
        m_url = str(row.get("minutes_listing_url", "") or "").strip() if pd.notna(row.get("minutes_listing_url")) else ""
        c_url = str(row.get("council_listing_url", "") or "").strip() if pd.notna(row.get("council_listing_url")) else ""
        m_has_js = any(d in m_url.lower() for d in JS_DOMAINS)
        c_has_js = any(d in c_url.lower() for d in JS_DOMAINS)
        if not m_has_js and c_has_js:
            try:
                r = requests.get(c_url, timeout=8, headers=hdr, verify=False)
                if r.status_code < 400:
                    df.at[idx, "minutes_listing_url"] = c_url
                    promoted += 1
                    print(f"  Promoted JS URL for {row['municipality_name']}: {c_url}")
            except Exception as exc:
                print(f"  WARN: {row['municipality_name']} council_listing_url check failed: {exc}")

    # 3b. Replace any dead-DNS council_listing_url with the row's live minutes_listing_url
    cleaned_council = 0
    for idx, row in df.iterrows():
        c_url = str(row.get("council_listing_url", "") or "").strip() if pd.notna(row.get("council_listing_url")) else ""
        m_url = str(row.get("minutes_listing_url", "") or "").strip() if pd.notna(row.get("minutes_listing_url")) else ""
        c_host = (urllib.parse.urlparse(c_url).hostname or "").lower()
        m_host = (urllib.parse.urlparse(m_url).hostname or "").lower()
        if c_host and not _dns_ok(c_host) and m_host and _dns_ok(m_host):
            df.at[idx, "council_listing_url"] = m_url
            cleaned_council += 1
            print(f"  Replaced dead council_listing_url for {row['municipality_name']}: {c_url} -> {m_url}")

    assert len(df) == 444, f"Row count changed to {len(df)}"
    df.to_csv(REGISTRY_PATH, index=False)
    print(
        f"Saved registry: direct_field_updates={direct_updates}, "
        f"scrubbed_examples={scrubbed}, promoted_js={promoted}, cleaned_dead_council={cleaned_council}"
    )

    # 4. Verification: duplicates and dead DNS hosts
    non_empty_m = df["minutes_listing_url"].dropna().astype(str).str.strip()
    non_empty_m = non_empty_m[non_empty_m != ""]
    vc = non_empty_m.value_counts()
    dups = vc[vc > 1]
    print(f"Duplicate non-empty minutes_listing_url count: {len(dups)}")
    if len(dups) > 0:
        print(dups)

    js_rows = df[df["portal_type"].astype(str).str.lower().isin(JS_TYPES)]
    js_m_hosts = sorted({
        (urllib.parse.urlparse(str(u).strip()).hostname or "").lower()
        for u in js_rows["minutes_listing_url"].dropna()
        if str(u).strip()
    })
    js_c_hosts = sorted({
        (urllib.parse.urlparse(str(u).strip()).hostname or "").lower()
        for u in js_rows["council_listing_url"].dropna()
        if str(u).strip()
    })
    with ThreadPoolExecutor(max_workers=24) as ex:
        dead_js_m = [h for h, ok in zip(js_m_hosts, ex.map(_dns_ok, js_m_hosts)) if not ok]
        dead_js_c = [h for h, ok in zip(js_c_hosts, ex.map(_dns_ok, js_c_hosts)) if not ok]
    print(f"Dead DNS hosts in JS minutes_listing_url: {len(dead_js_m)} {dead_js_m}")
    print(f"Dead DNS hosts in JS council_listing_url: {len(dead_js_c)} {dead_js_c}")

    all_m_hosts = sorted({
        (urllib.parse.urlparse(str(u).strip()).hostname or "").lower()
        for u in df["minutes_listing_url"].dropna()
        if str(u).strip()
    })
    all_c_hosts = sorted({
        (urllib.parse.urlparse(str(u).strip()).hostname or "").lower()
        for u in df["council_listing_url"].dropna()
        if str(u).strip()
    })
    with ThreadPoolExecutor(max_workers=24) as ex:
        dead_all_m = [h for h, ok in zip(all_m_hosts, ex.map(_dns_ok, all_m_hosts)) if not ok]
        dead_all_c = [h for h, ok in zip(all_c_hosts, ex.map(_dns_ok, all_c_hosts)) if not ok]
    print(f"Dead DNS hosts across ALL 444 minutes_listing_url: {len(dead_all_m)} {dead_all_m}")
    print(f"Dead DNS hosts across ALL 444 council_listing_url: {len(dead_all_c)} {dead_all_c}")


if __name__ == "__main__":
    main()
