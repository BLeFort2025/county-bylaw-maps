import docx
import sys

sys.stdout.reconfigure(encoding='utf-8')
doc_path = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps\How to use database\OFA Bylaw Database - User Onboarding Guide.docx"
doc = docx.Document(doc_path)

for i, para in enumerate(doc.paragraphs):
    if 130 <= i <= 190:
        print(f"[{i}] {para.text.strip()}")
