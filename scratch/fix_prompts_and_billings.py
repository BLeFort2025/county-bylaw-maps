import sqlite3
import glob

# 1. Update the prompts
prompt_files = glob.glob('signals/gemini_prompt_p3_batch_*.txt')
old_text = "Livestock Guardian Dogs (LGDs) are dogs used by farmers to protect livestock from predators. Related terms include:\n- **Livestock Guardian Dog** / **Guardian Dog** / **LGD**\n- **Working Dog** / **Farm Dog**\n- **Herding Dog**"

new_text = """Livestock Guardian Dogs (LGDs) are dogs used by farmers to protect livestock from predators. Related terms include:
- **Livestock Guardian Dog** / **Guardian Dog** / **LGD**
- **Working Dog** / **Farm Dog** (MUST be specific to agriculture/farming, NOT just police dogs or guard breeds like Boxers/Mastiffs)
- **Herding Dog**"""

for file in prompt_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {file}")

# 2. Update the database for Billings (bylaw_id=207)
conn = sqlite3.connect('bylaws.db')
c = conn.cursor()

c.execute("UPDATE bylaws SET progress_label = 'COMPLETE' WHERE id = 207")
c.execute("UPDATE details_lgd SET has_lgd_definition = 'No', lgd_definition = '' WHERE bylaw_id = 207")

conn.commit()
print(f"Updated Billings in database (bylaw_id=207). Rows affected: {c.rowcount}")
conn.close()
