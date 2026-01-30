import pandas as pd
import os

# The clean data that needs to be in the file
data = [
    ["AJAX TP","minutes_90d","2025-09-15","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://events.ajax.ca/Meetings/Detail/2025-09-15-1300-Council-Meeting",0.2,"needs_review"],
    ["BRANTFORD C","minutes_90d","2025-09-23","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://calendar.brantford.ca/meetings/Detail/2025-09-23-1800-City-Council",0.2,"needs_review"],
    ["BROCK TP","agenda_upcoming","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://pub-townshipofbrock.escribemeetings.com/Meeting.aspx?Agenda=PostMinutes&Id=7a8e1196-1c9f-4a9a-a3ba-239b4849de51&lang=English",0.2,"needs_review"],
    ["BURLINGTON C","agenda_upcoming","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://burlingtonpublishing.escribemeetings.com/Meeting.aspx?Id=5623816a-75a4-4ec3-9188-5e8ad474cc19&Agenda=Merged&lang=English",0.2,"needs_review"],
    ["CENTRAL ELGIN M","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://centralelgin.civicweb.net/filepro/documents/134005?handle=325B4562D4D74780AAA7C172A052169D",0.2,"needs_review"],
    ["CHATHAM KENT M","agenda_upcoming","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://pub-chatham-kent.escribemeetings.com/Meeting.aspx?Id=83633a45-4153-4ff4-a28d-d5a6014c5f63&Agenda=Agenda&lang=English",0.2,"needs_review"],
    ["EAST GWILLIMBURY TP","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://eastgwillimbury.civicweb.net/filepro/documents/199756",0.2,"needs_review"],
    ["HAWKESBURY T","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://hawkesbury.ca/en/town-hall/the-municipal-council/council-minutes",0.2,"needs_review"],
    ["OSHAWA C","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://pub-oshawa.escribemeetings.com/FileStream.ashx?DocumentId=13100",0.2,"needs_review"],
    ["PELEE TP","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://www.pelee.org/wp-content/uploads/2024/12/Regular-Council-Minutes-Dec-10-2024.pdf",0.2,"needs_review"],
    ["WELLESLEY TP","minutes_90d","2024-12-17","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://calendar.wellesley.ca/council/Detail/2024-12-17-1845-Regular-Council-Meeting/Minutes-2024-12-17.pdf",0.2,"needs_review"],
    ["WEST PERTH M","minutes_90d","2024-12-16","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://calendar.westperth.com/council/Detail/2024-12-16-1900-Regular-Council-Meeting/Minutes-2024-12-16.pdf",0.2,"needs_review"],
    ["ZORRA TP","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://zorra.civicweb.net/Portal/MeetingInformation.aspx?Id=1328",0.2,"needs_review"],
    ["DURHAM","minutes_90d","2025-12-17","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://calendar.durham.ca/meetings/Detail/2025-12-17-0930-Regional-Council-Meeting",0.2,"needs_review"],
    ["HASTINGS","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://hastingscounty.civicweb.net/Portal/MeetingInformation.aspx?Id=3200",0.2,"needs_review"],
    ["LAMBTON","minutes_90d","2025-12-03","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://calendar.lambtononline.ca/meetings/Detail/2025-12-03-0900-Council-Meeting/Minutes",0.2,"needs_review"],
    ["LANARK","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://lanarkcounty.civicweb.net/Portal/MeetingInformation.aspx?Id=2000",0.2,"needs_review"],
    ["MUSKOKA","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://muskoka.civicweb.net/Portal/MeetingInformation.aspx?Id=3000,0.2,needs_review"],
    ["NIAGARA","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://www.niagararegion.ca/government/council/minutes/default.aspx?t=1",0.2,"needs_review"],
    ["PERTH","minutes_90d","2026-01-12","2026-01-12","Potential DC Mention","Scanner detected DC keywords. Context unavailable in V1 output.","https://perthcounty.civicweb.net/Portal/MeetingInformation.aspx?Id=1000",0.2,"needs_review"]
]

columns = ["munid","signal_type","meeting_date","discovered_date","topic","snippet","evidence_url","confidence","review_status"]

# Create DataFrame
df = pd.DataFrame(data, columns=columns)

# Define path (relative to where you run it)
output_path = r"..\signals\signals.csv"

# Ensure directory exists
os.makedirs(os.path.dirname(output_path), exist_ok=True)

# Save as PURE CSV (no index, no binary excel junk)
df.to_csv(output_path, index=False)

print(f"SUCCESS! Clean CSV saved to: {os.path.abspath(output_path)}")