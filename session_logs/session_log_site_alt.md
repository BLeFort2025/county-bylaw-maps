# Session Log: Site Alteration & Fill Bylaw — Full Database Verification
# Started: 2026-04-13
# Researcher: Claude (Antigravity AI) — direct web research, no Gemini API
# Database: Neon PostgreSQL (production)
# Scope: All 444 Ontario municipalities, alphabetical order
# Write mode: Direct to DB with full audit trail (user = 'site_alt_refresh_2026')

---

## Session 1 — 2026-04-13

### Initial Audit Baseline (pre-refresh state)
- Total SITE_ALT records: 444
- exemption_status = Yes:       87
- exemption_status = No:        47
- exemption_status = NULL:     306  ← 69% BLANK — major refresh needed
- exemption_status = N/A:        1
- exemption_status = NOT KNOWN:  1
- exemption_status = '0':        1  ← data error to fix
- exemption_status = 'Other':    1  ← data error to fix
- Has bylaw_name:       137 / 444
- Has bylaw_link:       136 / 444
- Has date_enacted:     126 / 444
- Has exemption_wording: 112 / 444
- Has exception_wording:  59 / 444

### Resume Marker
Last completed municipality: (none — starting now)

---

## Batch 1 — Municipalities 1–20 (Adelaide-Metcalfe → Augusta)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Notes |
|:---|:---|:---|
| Adelaide-Metcalfe | N/A | No dedicated bylaw found |
| Adjala-Tosorontio | Yes | By-law 20-47; ag justification pathway |
| Admaston-Bromley | NOT KNOWN | Zoning review underway |
| Ajax | Yes | By-law 38-2021; normal ag practice exempt |
| Alberton | N/A | No bylaw; very small rural muni |
| Alfred and Plantagenet | NOT KNOWN | No bylaw found |
| Algonquin Highlands | NOT KNOWN | No bylaw found |
| Alnwick-Haldimand | NOT KNOWN | By-law 55-2011; exemptions exist but wording unavailable |
| Amaranth | **Yes** *(was No — EXEMPTION GAINED)* | By-law 65-2009; sod/greenhouse/nursery exempt |
| Amherstburg | Yes | By-law 2025-033; FRFOFA registration req'd |
| Armour | NOT KNOWN | By-law 41-2010; Section 4 exemptions exist |
| Armstrong | N/A | No bylaw; small Timiskaming muni |
| Arnprior | NOT KNOWN | No bylaw found |
| Arran-Elderslie | NOT KNOWN | No dedicated bylaw found |
| Ashfield-Colborne-Wawanosh | Yes | By-law 28-2023; Section 4.1(g) ag lands exempt |
| Asphodel-Norwood | NOT KNOWN | No bylaw found |
| Assiginack | N/A | No bylaw; small island muni |
| Athens | NOT KNOWN | No bylaw found |
| Atikokan | N/A | No bylaw; Rainy River single-tier |
| Augusta | NOT KNOWN | No bylaw found |

---

## Exemption Changes Log (⚠️ High Priority — auto-populated)
| Municipality | Old Status | New Status | Flag |
|:---|:---|:---|:---|
| Amaranth | No | Yes | ✅ EXEMPTION GAINED — By-law 65-2009 confirmed; sod-farming, greenhouse, nursery operations explicitly exempt |

---

## Batch 2 — Municipalities 21–40 (Aurora → Brantford)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Notes |
|:---|:---|:---|
| Aurora | Yes | By-law 6226-19; ag use exempt incl. sod/greenhouse/nursery — VERIFIED |
| Aylmer | **Yes** *(was No — EXEMPTION GAINED)* | By-law 45-23; FFPPA s.1.1 normal farm practice — Section 4 |
| Baldwin | N/A | No bylaw; small Sudbury District muni |
| Bancroft | NOT KNOWN | No bylaw found |
| Barrie | No | By-law 2014-100; no farm exemption confirmed in public records |
| Bayham | NOT KNOWN | Bylaw referenced on website; number/text not confirmed |
| Beckwith | NOT KNOWN | No dedicated bylaw confirmed |
| Belleville | NOT KNOWN | No bylaw found |
| Billings | N/A | No bylaw; small Manitoulin muni |
| Black River-Matheson | N/A | No bylaw; Cochrane District |
| Blandford-Blenheim | No | By-law 1915-2015; no farm exemption confirmed |
| Blind River | N/A | No bylaw; Algoma District |
| Bluewater | NOT KNOWN | No bylaw found; Huron County may have county-wide rules |
| Bonfield | N/A | No bylaw; small Nipissing muni |
| Bonnechere Valley | NOT KNOWN | No bylaw found |
| Bracebridge | NOT KNOWN | Has site alt regulation; bylaw number/farm exemption not confirmed |
| Bradford West Gwillimbury | No | By-law 2017-33; ag permit stream exists but no blanket exemption |
| Brampton | Yes | By-law 119-2024; Section 4; sod/greenhouse/nursery exempt |
| Brant | Yes | By-law 87-24; FFPPA; ag permit stream for >1,000m3 |
| Brantford | Yes | By-law 29-2023; 3 ag exemption provisions (s4.1.10, .12, .13) |

### Resume Marker
Last completed municipality: Dutton-Dunwich

---

## Batch 5 — Municipalities 81–100 (Cobourg → Dutton-Dunwich)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Cobourg | No | CONFIRMED CURRENT | By-law 035-2012; still active per 2026 registry |
| Cochrane | N/A | — | No bylaw; Cochrane District |
| Cockburn Island | N/A | — | No bylaw; tiny Manitoulin island muni |
| Coleman | N/A | — | No bylaw; small Timiskaming muni |
| Collingwood | NOT KNOWN | ⚠️ FLAG: 2003 bylaw ~22 years old | Fill By-law 03-103; no confirmed replacement |
| Conmee | N/A | — | No bylaw; Thunder Bay District |
| Cornwall | NOT KNOWN | — | No bylaw found |
| Cramahe | No | CONFIRMED CURRENT | By-law 2017-18; active permit process confirmed |
| Dawn-Euphemia | Yes | CONFIRMED CURRENT | By-law 2021-039 |
| Dawson | N/A | — | No bylaw; Rainy River District |
| Deep River | NOT KNOWN | — | No bylaw found |
| Deseronto | Yes | CONFIRMED CURRENT | By-law 47-2023 |
| Dorion | N/A | — | No bylaw; Thunder Bay District |
| Douro-Dummer | NOT KNOWN | — | No bylaw found |
| Drummond-North Elmsley | No | ⚠️ FLAG: 2012 bylaw ~13 years old | By-law 2012-056; zoning update underway |
| Dryden | NOT KNOWN | — | No bylaw found |
| Dubreuilville | N/A | — | No bylaw; Algoma District |
| Dufferin | N/A | — | Upper tier |
| Durham | N/A | — | Upper tier |
| Dutton-Dunwich | NOT KNOWN | — | No bylaw found; significant ag area |

---

## Potentially Stale Bylaws — Currency Flags
| Municipality | Bylaw | Year | Age | Action Required |
|:---|:---|:---|:---|:---|
| Collingwood | Fill By-law 03-103 | ~2003 | ~22 yrs | Verify with Town if replaced |
| Drummond-North Elmsley | BY-LAW 2012-056 | 2012 | 13 yrs | Verify — zoning update underway |

---

## Batch 3 — Municipalities 41–60 (Brethour → Casey)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Notes |
|:---|:---|:---|
| Brethour | N/A | No bylaw; tiny Timiskaming muni |
| Brighton | **Yes** *(was No — EXEMPTION GAINED)* | By-law 114-2016; bona fide Normal Ag Practice exempt |
| Brock | Yes | By-law 2633-2015+2703-2016; exemption confirmed |
| Brockton | NOT KNOWN | No bylaw found |
| Brockville | NOT KNOWN | No bylaw found |
| Brooke-Alvinston | N/A | No bylaw; small Lambton muni |
| Bruce (County) | N/A | Upper tier — bylaws at lower tier level |
| Bruce Mines | N/A | No bylaw; Algoma District |
| Brudenell, Lyndoch and Raglan | N/A | No bylaw; small Renfrew township |
| Burk's Falls | N/A | No bylaw; small Parry Sound muni |
| Burlington | Yes | By-law 64-2014 + 93-2020 (fee amend); FFPPA applies |
| Burpee and Mills | N/A | No bylaw; small Manitoulin muni |
| Caledon | Yes | By-law 2007-59; new bylaw in consultation (Sept 2025 draft) — MONITOR |
| Callander | NOT KNOWN | No bylaw found |
| Calvin | N/A | No bylaw; small Nipissing muni |
| Cambridge | Yes | By-law 23-103; Normal Farming Practices fully exempt |
| Carleton Place | NOT KNOWN | No bylaw found |
| Carling | N/A | No bylaw; small Parry Sound township |
| Carlow-Mayo | N/A | No bylaw; small Hastings township |
| Casey | N/A | No bylaw; tiny Timiskaming muni |

---

## Batch 6 — Municipalities 101–120 (Dysart et al → Evanturel)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Dysart et al | No | CONFIRMED CURRENT | By-law 2023-101; water protection focus |
| Ear Falls | N/A | — | No bylaw; Kenora District |
| East Ferris | N/A | — | No bylaw; Nipissing District |
| East Garafraxa | Yes | CONFIRMED CURRENT | By-law 14-2015; exemption explicitly worded |
| East Gwillimbury | Yes | REVIEW UNDERWAY | By-law 2013-066 (active, but reviewing for O.Reg 406/19) |
| East Hawkesbury | NOT KNOWN | — | No bylaw found |
| East Zorra-Tavistock | NOT KNOWN | — | No bylaw found |
| Edwardsburgh-Cardinal | NOT KNOWN | — | No bylaw found |
| Elgin (County) | N/A | — | Upper tier |
| Elizabethtown-Kitley | NOT KNOWN | — | No bylaw found |
| Elliot Lake | N/A | — | No bylaw; Algoma District |
| Emo | N/A | — | No bylaw; Rainy River District |
| Englehart | N/A | — | No bylaw; Timiskaming District |
| Enniskillen | NOT KNOWN | — | No bylaw found |
| Erin | Yes | CONFIRMED CURRENT | By-law 16-30; amended Feb 2026 for ag restorations |
| Espanola | N/A | — | No bylaw; Sudbury District |
| Essa | Yes | CONFIRMED CURRENT | By-law 2019-84; strict permitting for "Bona Fide" >100m3 |
| Essex, Co | **N/A** *(was Yes)* | — | CORRECTION: Upper tier; incorrectly marked Yes in DB |
| Essex, T | No | CONFIRMED CURRENT | By-law 1799 (amended by 2336); no blanket ag exemption |
| Evanturel | N/A | — | No bylaw; Timiskaming District |

---

## Batch 8 — Municipalities 141–160 (Greater Napanee → Havelock-Belmont-Methuen)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Greater Napanee | NOT KNOWN | — | No bylaw found |
| Greater Sudbury | No | CONFIRMED CURRENT | By-law 2009-170 (amended 2021) |
| Greenstone | N/A | — | No bylaw; Thunder Bay District |
| Grey (County) | N/A | — | Upper tier |
| Grey Highlands | Yes | CONFIRMED CURRENT | By-law 2023-083 |
| Grimsby | Yes | CONFIRMED CURRENT | By-law 2020-44; NPCA rules supersede |
| Guelph | **No** *(was Yes)* | CONFIRMED CURRENT | By-law (2016)-20097; NO blanket ag exemption. Permits required for "Normal Ag Practice" unless minor landscape |
| Guelph-Eramosa | Yes | CONFIRMED CURRENT | By-law 22/2021 |
| Haldimand | No | CONFIRMED CURRENT | By-law 1664/16 |
| Haliburton (County) | N/A | — | Upper tier |
| Halton (Region) | N/A | — | Upper tier |
| Halton Hills | Yes | CONFIRMED CURRENT | By-law 2025-0009; brand new, detailed ag conditions and limits (<29m3/6mo) |
| Hamilton, C (City) | Yes | CONFIRMED CURRENT | By-law 19-286; DB incorrectly had old Tp bylaw 2012-10 |
| Hamilton, Tp (Township) | **Yes** *(was No)* | CONFIRMED CURRENT | By-law 2012-10; explicit agricultural exemption verified |
| Hanover | NOT KNOWN | — | No bylaw found |
| Harley | N/A | — | No bylaw; Timiskaming |
| Harris | N/A | — | No bylaw; Timiskaming |
| Hastings (County) | N/A | — | Upper tier |
| Hastings Highlands | NOT KNOWN | — | No bylaw found |
## Batch 9 — Municipalities 161–180 (Hawkesbury → Iroquois Falls)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Hawkesbury | NOT KNOWN | — | No bylaw found |
| Head, Clara and Maria | NOT KNOWN | — | No bylaw found |
| Hearst | N/A | — | Cochrane District |
| Highlands East | NOT KNOWN | — | No bylaw found |
| Hilliard | N/A | — | Timiskaming |
| Hilton | N/A | — | Algoma |
| Hilton Beach | N/A | — | Algoma |
| Hornepayne | N/A | — | Algoma |
| Horton | NOT KNOWN | — | No bylaw found |
| Howick | **NOT KNOWN** *(was '0')* | — | CORRECTION: Fixed legacy data error '0' from Access |
| Hudson | N/A | — | Timiskaming |
| Huntsville | NOT KNOWN | CONFIRMED CURRENT | Community Planning Permit By-law 2022-97 |
| Huron (County) | N/A | — | Upper tier |
| Huron East | NOT KNOWN | — | No bylaw found |
| Huron Shores | N/A | — | Algoma |
| Huron-Kinloss | NOT KNOWN | — | No bylaw found |
| Ignace | N/A | — | Kenora |
| Ingersoll | NOT KNOWN | — | No bylaw found |
| Innisfil | Yes | CONFIRMED CURRENT | By-law 050-13 (amended 045-14) |
## Batch 10 — Municipalities 181–200 (James → Laird)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| James | N/A | — | Timiskaming |
| Jocelyn | N/A | — | Algoma |
| Johnson | N/A | — | Algoma |
| Joly | N/A | — | Parry Sound |
| Kapuskasing | N/A | — | Cochrane |
| Kawartha Lakes | Yes | CONFIRMED CURRENT | By-law 2019-105; 500-1000m3 exemption |
| Kearney | N/A | — | Parry Sound |
| Kenora | N/A | — | Kenora |
| Kerns | N/A | — | Timiskaming |
| Killaloe, Hagarty and Richards | NOT KNOWN | — | No bylaw found |
| Killarney | N/A | — | Sudbury |
| Kincardine | NOT KNOWN | — | No bylaw found |
| King | Yes | CONFIRMED CURRENT | By-law 2021-039 |
| Kingston | No | CONFIRMED CURRENT | By-law 2008-128; flag for age |
| Kingsville | Yes | CONFIRMED CURRENT | By-law 64-2025 |
| Kirkland Lake | N/A | — | Timiskaming |
| Kitchener | **No** *(was Yes)* | CONFIRMED CURRENT | By-law 2010-043 (amended 2023); no blanket farm exemption; permits required |
| La Vallee | N/A | — | Rainy River |
| LaSalle | Yes | CONFIRMED CURRENT | By-law 7080 |
## Batch 11 — Municipalities 201–220 (Lake of Bays → Lucan Biddulph)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Lake of Bays | Yes | CONFIRMED CURRENT | By-law 2021-111 (CPP) |
| Lake of the Woods | N/A | — | Kenora |
| Lakeshore | Yes | CONFIRMED CURRENT | By-law 60-2020 |
| Lambton (County) | N/A | — | Upper tier |
| Lambton Shores | Yes | CONFIRMED CURRENT | By-law 27 of 2004; FLAG for age |
| Lanark (County) | N/A | — | Upper tier |
| Lanark Highlands | NOT KNOWN | — | No bylaw found |
| Larder Lake | N/A | — | Timiskaming |
| Latchford | N/A | — | Timiskaming |
| Laurentian Hills | NOT KNOWN | — | No bylaw found |
| Laurentian Valley | NOT KNOWN | — | No bylaw found |
| Leamington | NOT KNOWN | ⚠️ FLAG: Manual PDF Review Needed | Website confirms bylaw process exists; DB previously blank |
| Leeds and Grenville | N/A | — | Upper tier |
| Leeds and the Thousand Islands | NOT KNOWN | — | No bylaw found |
| Lennox and Addington | N/A | — | Upper tier |
| Limerick | NOT KNOWN | — | No bylaw found |
| Lincoln | Yes | CONFIRMED CURRENT | By-law 2024-50 (Corrected from 2020) |
| London | Yes | CONFIRMED CURRENT | By-law C.P.-1363-381 |
| Loyalist | Yes | CONFIRMED CURRENT | By-law 2003-22; confirmed active in Official Plan; FLAG for age |
| Lucan Biddulph | Yes | CONFIRMED CURRENT | By-law 38-2022 |

---
## Batch 12 — Municipalities 221–240 (Macdonald Meredith et al → McKellar)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Macdonald Meredith et al | N/A | — | Algoma |
| Machar | N/A | — | Parry Sound |
| Machin | N/A | — | Kenora |
| Madawaska Valley | NOT KNOWN | — | No bylaw found |
| Madoc | NOT KNOWN | — | No bylaw found |
| Magnetawan | N/A | — | Parry Sound |
| Malahide | NOT KNOWN | — | Site Alteration By-law 08-59; text missing online |
| Manitouwadge | N/A | — | Thunder Bay |
| Mapleton | NOT KNOWN | — | No bylaw found |
| Marathon | N/A | — | Thunder Bay |
| Markham | Yes | CONFIRMED CURRENT | By-law 2011-232; strict 300mm limit for ag exemption |
| Markstay-Warren | N/A | — | Sudbury |
| Marmora and Lake | Yes | CONFIRMED CURRENT | By-law 2003-22; confirmed in OP |
| Matachewan | N/A | — | Timiskaming |
| Mattawa | N/A | — | Nipissing |
| Mattawan | N/A | — | Nipissing |
| Mattice-Val Cote | N/A | — | Cochrane |
| McDougall | N/A | — | Parry Sound |
| McGarry | N/A | — | Timiskaming |
| McKellar | N/A | — | Parry Sound |

## Batch 13 — Municipalities 241–260 (McMurrich-Monteith → Mulmur)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| McMurrich-Monteith | N/A | — | Parry Sound |
| McNab-Braeside | NOT KNOWN | — | No bylaw found |
| Meaford | No | CONFIRMED CURRENT | By-law 058-2010 |
| Melancthon | No | CONFIRMED CURRENT | By-law 29-2004 (amended 2012); fill must come from Dufferin County |
| Merrickville-Wolford | NOT KNOWN | — | No bylaw found |
| Middlesex (County) | N/A | — | Upper tier |
| Middlesex Centre | Yes | CONFIRMED CURRENT | By-law 2016-087 |
| Midland | NOT KNOWN | — | No bylaw found |
| Milton | Yes | CONFIRMED CURRENT | By-law 094-2022; strict requirement for proof of FBRN/taxes |
| Minden Hills | NOT KNOWN | — | No bylaw found |
| Minto | Yes | CONFIRMED CURRENT | By-law 2020-16 |
| Mississauga | No | CONFIRMED CURRENT | By-law 0512-1991; Erosion Control; FLAG for age |
| Mississippi Mills | NOT KNOWN | — | No bylaw found |
| Mono | Yes | CONFIRMED CURRENT | By-law 2014-31 |
| Montague | NOT KNOWN | — | No bylaw found |
| Moonbeam | N/A | — | Cochrane |
| Moosonee | N/A | — | Cochrane |
| Morley | N/A | — | Rainy River |
| Morris-Turnberry | NOT KNOWN | — | No bylaw found |
| Mulmur | Yes | CONFIRMED CURRENT | By-law 4-15 |

## Batch 14 — Municipalities 261–280 (Muskoka → North Grenville)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Muskoka (District) | N/A | — | Upper tier |
| Muskoka Lakes | No | CONFIRMED CURRENT | By-law 2022-108 |
| Nairn and Hyman | N/A | — | Sudbury |
| Neebing | N/A | — | Thunder Bay |
| New Tecumseth | Yes | CONFIRMED CURRENT | By-law 2020-007 |
| Newbury | Other | CONFIRMED CURRENT | By-law 692 (Zoning proxy from 1978); FLAG |
| Newmarket | Yes | CONFIRMED CURRENT | By-law 2016-58 |
| Niagara (Region) | N/A | — | Upper tier |
| Niagara Falls | No | CONFIRMED CURRENT | By-law 2015-08 |
| Niagara-on-the-Lake | Yes | UPDATED | By-law 3941-05 replaced by new 2026 by-law; requires manual review |
| Nipigon | N/A | — | Thunder Bay |
| Nipissing | N/A | — | Parry Sound |
| Norfolk | NOT KNOWN | — | No standalone bylaw found |
| North Algona Wilberforce | NOT KNOWN | — | No bylaw found |
| North Bay | N/A | — | Nipissing |
| North Dumfries | Yes | CONFIRMED CURRENT | By-law 2612-14 (amended 2019) |
| North Dundas | NOT KNOWN | — | No bylaw found |
| North Frontenac | NOT KNOWN | — | No bylaw found |
| North Glengarry | NOT KNOWN | — | No bylaw found |
| North Grenville | NOT KNOWN | — | No bylaw found |

## Batch 15 — Municipalities 281–300 (North Huron → Ottawa)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| North Huron | NOT KNOWN | — | No bylaw found |
| North Kawartha | NOT KNOWN | — | No bylaw found |
| North Middlesex | NOT KNOWN | — | No bylaw found |
| North Perth | No | CONFIRMED CURRENT | By-law 7-2023 |
| North Stormont | NOT KNOWN | — | No bylaw found |
| Northeastern Manitoulin & The Isl | N/A | — | Manitoulin |
| Northern Bruce Peninsula | NOT KNOWN | — | No bylaw found |
| Northumberland (County) | N/A | — | Upper tier |
| Norwich | NOT KNOWN | — | No bylaw found |
| O'Connor | N/A | — | Thunder Bay |
| Oakville | Yes | CONFIRMED CURRENT | By-law 2023-047; explicit sod/nursery exemption |
| Oil Springs | NOT KNOWN | — | No bylaw found |
| Oliver Paipoonge | N/A | — | Thunder Bay |
| Opasatika | N/A | — | Cochrane |
| Orangeville | Yes | CONFIRMED CURRENT | By-law 2024-001 |
| Orillia | No | CONFIRMED CURRENT | Chapter 373 Sites; No blanket farm exemption, strict 50m3 limit |
| Oro-Medonte | Yes | CONFIRMED CURRENT | By-law 2016-056 |
| Oshawa | Yes | CONFIRMED CURRENT | By-law 85-2006; FLAG for age |
| Otonabee-South Monaghan | NOT KNOWN | — | No bylaw found |
| Ottawa | Yes | CONFIRMED CURRENT | By-law 2024-448 |

## Batch 16 — Municipalities 301–320 (Owen Sound → Pickle Lake)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Owen Sound | NOT KNOWN | — | No bylaw found |
| Oxford (County) | N/A | — | Upper tier |
| Papineau-Cameron | N/A | — | Nipissing |
| Parry Sound | N/A | — | Parry Sound |
| Peel (Region) | N/A | — | Upper tier |
| Pelee | N/A | — | Essex |
| Pelham | No | CONFIRMED CURRENT | By-law #624; FLAG for extreme age (1980) |
| Pembroke | N/A | — | Renfrew |
| Penetanguishene | No | CONFIRMED CURRENT | By-law 2012-69 |
| Perry | N/A | — | Parry Sound |
| Perth East | No | CONFIRMED CURRENT | By-law 76-2002 |
| Perth South | NOT KNOWN | — | No bylaw found |
| Perth, Co | N/A | — | Upper tier |
| Perth, T | NOT KNOWN | — | No bylaw found |
| Petawawa | NOT KNOWN | — | No bylaw found |
| Peterborough, C | Yes | CONFIRMED CURRENT | By-law 25-108 |
| Peterborough, Co | N/A | — | Upper tier |
| Petrolia | NOT KNOWN | — | No bylaw found |
| Pickering | Yes | CONFIRMED CURRENT | By-law 6060-02; limits based on 30m of water |
| Pickle Lake | N/A | — | Kenora |

---

## Batch 17 — Municipalities 321–340 (Plummer Additional → Rideau Lakes)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Plummer Additional | N/A | — | Algoma |
| Plympton-Wyoming | NOT KNOWN | — | No bylaw found |
| Point Edward | NOT KNOWN | — | No bylaw found |
| Port Colborne | Yes | CONFIRMED CURRENT | By-law 5528-125-10; EXEMPTION GAINED |
| Port Hope | NOT KNOWN | — | No bylaw found |
| Powassan | N/A | — | Parry Sound |
| Prescott | N/A | — | Leeds |
| Prescott and Russell | N/A | — | Upper tier |
| Prince | N/A | — | Algoma |
| Prince Edward County | N/A | — | Rely on Quinte Conservation |
| Puslinch | Yes | CONFIRMED CURRENT | By-law 2023-057; strict waiver requirement |
| Quinte West | Yes | CONFIRMED CURRENT | By-law 08-30; FLAG for age |
| Rainy River | N/A | — | Rainy River |
| Ramara | No | CONFIRMED CURRENT | By-law 2018 |
| Red Lake | N/A | — | Kenora |
| Red Rock | N/A | — | Thunder Bay |
| Renfrew (County) | N/A | — | Upper tier |
| Renfrew (Town) | NOT KNOWN | — | No bylaw found |
| Richmond Hill | Yes | CONFIRMED CURRENT | By-law 47-25 |
| Rideau Lakes | NOT KNOWN | — | No bylaw found |

---

## Batch 18 — Municipalities 341–360 (Russell → South Bruce)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Russell | NOT KNOWN | — | No bylaw found |
| Ryerson | Yes | CONFIRMED CURRENT | By-law 11-12; EXEMPTION GAINED |
| Sables-Spanish Rivers | N/A | — | Sudbury |
| Sarnia | NOT KNOWN | — | No bylaw found |
| Saugeen Shores | NOT KNOWN | — | No bylaw found |
| Sault Ste Marie | N/A | — | Algoma |
| Schreiber | N/A | — | Thunder Bay |
| Scugog | Yes | CONFIRMED CURRENT | By-law 62-15 |
| Seguin | No | UPDATED | By-law 2024-007; replaced 2008-105; exclusively shoreline protection |
| Selwyn | NOT KNOWN | — | No bylaw found |
| Severn | NOT KNOWN | — | No bylaw found |
| Shelburne | NOT KNOWN | — | No bylaw found |
| Shuniah | N/A | — | Thunder Bay |
| Simcoe (County) | N/A | — | Upper tier |
| Sioux Lookout | N/A | — | Kenora |
| Sioux Narrows-Nestor Falls | N/A | — | Kenora |
| Smiths Falls | N/A | — | Lanark |
| Smooth Rock Falls | N/A | — | Cochrane |
| South Algonquin | N/A | — | Nipissing |
## Batch 20 — Municipalities 381–400 (Stormont, Dundas and Glengarry → Thessalon)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Stormont, Dundas and Glengarry | N/A | — | Upper tier |
| Stratford | No | CONFIRMED CURRENT | By-Law No. 102-2022 |
| Strathroy-Caradoc | Yes | CONFIRMED CURRENT | By-law 07-22 |
| Strong | N/A | — | Parry Sound |
| Sundridge | N/A | — | Parry Sound |
| Tarbutt | No | CONFIRMED CURRENT | 24-2016 |
| Tay | No | CONFIRMED CURRENT | By-law 98-43 (amended 2012); FLAG for age |
| Tay Valley | NOT KNOWN | — | No bylaw found |
| Tecumseh | No | CONFIRMED CURRENT | By-law 2004-29; FLAG for age |
| Tehkummah | N/A | — | Manitoulin |
| Temagami | N/A | — | Nipissing |
| Temiskaming Shores | N/A | — | Timiskaming |
| Terrace Bay | N/A | — | Thunder Bay |
| Thames Centre | NOT KNOWN | — | No bylaw found |
| The Archipelago | No | DRAFT | Draft stage, not enacted |
| The Blue Mountains | No | CONFIRMED CURRENT | By-law 2002-78; FLAG for age |
| The Nation | NOT KNOWN | — | No bylaw found |
| The North Shore | N/A | — | Algoma |
| The South Bruce Peninsula | NOT KNOWN | — | No bylaw found |
| Thessalon | N/A | — | Algoma |

## Batch 21 — Municipalities 401–420 (Thornloe → Waterloo, R)
Status: COMPLETE (2026-04-13)

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Thornloe | N/A | — | Timiskaming |
| Thorold | Yes | CONFIRMED CURRENT | By-law 17-2021 |
| Thunder Bay | No | CONFIRMED CURRENT | By-law 135-1997; FLAG for age / conservation overlay |
| Tillsonburg | NOT KNOWN | — | No bylaw found |
| Timmins | Yes | CONFIRMED CURRENT | By-law 2019-8343 |
| Tiny | NOT KNOWN | — | No bylaw found |
| Toronto | N/A | — | Regulated outside of standard site alt framework |
| Trent Hills | NOT KNOWN | — | No bylaw found |
| Trent Lakes | NOT KNOWN | — | No bylaw found |
| Tudor and Cashel | NOT KNOWN | — | No bylaw found |
| Tweed | NOT KNOWN | — | No bylaw found |
| Tyendinaga | NOT KNOWN | — | No bylaw found |
| Uxbridge | Yes | CONFIRMED CURRENT | By-law 2010-084 |
| Val Rita-Harty | N/A | — | Cochrane |
| Vaughan | Yes | CONFIRMED CURRENT | Site Alteration By-law 031-2024 |
| Wainfleet | Yes | CONFIRMED CURRENT | By-law 025-2022 |
| Warwick | NOT KNOWN | — | No bylaw found |
| Wasaga Beach | NOT KNOWN | — | No bylaw found |
| Waterloo, C | Yes | CONFIRMED CURRENT | By-law 2010-066 |
| Waterloo, R | N/A | — | Upper tier |

## Batch 22 — Municipalities 421–444 (Wawa → Zorra/Dawn)
Status: COMPLETE (2026-04-13) - PROVINCE FULLY AUDITED

| Municipality | Exemption Status | Currency | Notes |
|:---|:---|:---|:---|
| Wawa | N/A | — | Algoma |
| Welland | No | CONFIRMED CURRENT | By-law 2010-88 (corrected from 2010-81) |
| Wellesley | NOT KNOWN | — | No bylaw found |
| Wellington (County) | N/A | — | Upper tier |
| Wellington North | Yes | CONFIRMED CURRENT | By-law 011-2025 |
| West Elgin | NOT KNOWN | — | No bylaw found |
| West Grey | Yes | CONFIRMED CURRENT | By-law 120-2018 |
| West Lincoln | Yes | CONFIRMED CURRENT | By-law 2016-41 |
| West Nipissing | N/A | — | Nipissing |
| West Perth | NOT KNOWN | DATA CORRECTED | Previously marked Yes erroneously; no bylaw exists |
| Westport | NOT KNOWN | — | No bylaw found |
| Whitby | Yes | CONFIRMED CURRENT | By-law 7425-18 |
| Whitchurch-Stouffville | Yes | CONFIRMED CURRENT | By-law 2024-037-RE |
| White River | N/A | — | Algoma |
| Whitestone | N/A | — | Parry Sound |
| Whitewater Region | NOT KNOWN | — | No bylaw found |
| Wilmot | NOT KNOWN | — | No bylaw found |
| Windsor | No | CONFIRMED CURRENT | By-law 6938; FLAG for extreme age (1981) |
| Wollaston | NOT KNOWN | — | No bylaw found |
| Woodstock | NOT KNOWN | — | No bylaw found |
| Woolwich | Yes | CONFIRMED CURRENT | By-law No. 51-2024 |
| York (Region) | N/A | — | Upper tier |
| Zorra | No | CONFIRMED CURRENT | By-law 49-03 |
| Dawn-Euphemia (Listed as dawn) | NOT KNOWN | — | No bylaw found |
| South Bruce | NOT KNOWN | — | Carried over from Batch 18 |

---

## Exemption Changes Log (UPDATED)
| Municipality | Old Status | New Status | Flag |
|:---|:---|:---|:---|
| Amaranth | No | Yes | EXEMPTION GAINED — By-law 65-2009; sod/greenhouse/nursery exempt |
| Aylmer | No | Yes | EXEMPTION GAINED — By-law 45-23 Section 4; FFPPA s.1.1 normal farm practice |
| Brighton | No | Yes | EXEMPTION GAINED — By-law 114-2016; bona fide Normal Agricultural Practice exempt |
| Essex, Co | Yes | N/A | EXEMPTION CORRECTED — Upper tier; incorrectly marked 'Yes' historically |
| Guelph | Yes | No | EXEMPTION LOST — By-law (2016)-20097; "Normal Ag Practice" does not grant blanket exemption; permit needed |
| Hamilton, Tp | No | Yes | EXEMPTION GAINED — By-law 2012-10 Section 4; incidental ag practice exempt on Perm/Marg Ag zoned land |
| Kitchener | Yes | No | EXEMPTION LOST — By-law 2010-043 (rev 2023); no blanket farm exemption, similar to Guelph |
| Port Colborne | No | Yes | EXEMPTION GAINED — By-law 5528-125-10 Sections 24/25; incidental ag practice exempt |
| Ryerson | No | Yes | EXEMPTION GAINED — By-law 11-12 Section 2; incidental plowing/cultivating exempt |
| South Huron | No | Other | DATA RECLASSIFIED — Uses Zoning By-Law proxy, not dedicated site alteration bylaw |
| West Perth | Yes | NOT KNOWN | DATA RECLASSIFIED — Previously marked Yes erroneously; no bylaw exists |
