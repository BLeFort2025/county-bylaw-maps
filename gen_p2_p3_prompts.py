import pandas as pd
import os
import math

# Use the current working directory since we run it from root
SCRIPT_DIR = os.getcwd()
SIGNALS_DIR = os.path.join(SCRIPT_DIR, "signals")

# Base prompt template for search-based extraction
PROMPT_TEMPLATE = """# TASK: Extract Livestock Guardian Dog (LGD) Bylaw Data — {phase} Batch {batch_num}

## Context
I am a policy analyst at the Ontario Federation of Agriculture (OFA). We maintain a database tracking how all 444 Ontario municipalities regulate Livestock Guardian Dogs (LGDs) in their animal control bylaws. For the municipalities in this batch, we need to verify their current bylaw. I need you to **search the web for each municipality's current animal control or dog licensing bylaw**, find the correct document, read it, and extract the data fields below.

## What to Look For
"Livestock Guardian Dogs" (LGDs) are dogs used by farmers to protect livestock from predators. Related terms include:
- **Livestock Guardian Dog** / **Guardian Dog** / **LGD**
- **Working Dog** / **Farm Dog**
- **Herding Dog**
- **Kennel exemptions for agricultural properties**

## Municipalities to Process

For each municipality below, please search their official website (e.g. "[municipality name] animal control bylaw" or "[municipality name] dog bylaw") to find their current animal control bylaw document.

{municipality_list}

## Instructions
For EACH municipality above:
1. **Search the municipality's official website** to find their current animal control / dog bylaw document.
2. **Read the full bylaw** and extract ALL of the following fields into the JSON format specified below.
3. If you truly cannot find any animal control or dog bylaw for the municipality despite searching, note "BYLAW NOT FOUND" in the notes field and set the progress_label to "NO BY-LAW IN PLACE". Fill in the other fields with null or "N/A".

## Required Fields (extract for each municipality)

```json
{
  "municipality": "Name of municipality",
  "county": "County/Region name",
  "bylaw_name": "The official bylaw name/number exactly as written in the document (e.g. 'BY-LAW NUMBER 2024-045')",
  "date_enacted": "Date the bylaw was enacted in YYYY-MM-DD format, or null if not found",
  "has_lgd_definition": "Yes or No - does the bylaw explicitly define 'livestock guardian dog', 'working dog', or 'farm dog'?",
  "lgd_definition": "The EXACT quoted text of the LGD/working dog/farm dog definition from the bylaw, or null if none exists",
  "has_herding_def": "Yes or No - does the bylaw explicitly define 'herding dog'?",
  "herding_definition": "The EXACT quoted text of the herding dog definition, or null",
  "exempt_license_fees": "Yes if LGDs/working dogs are exempt from license fees, No if they must pay, N/A if license fees aren't mentioned",
  "collar_tag_req": "Description of any collar/tag requirements for dogs, or null",
  "barking_restrictions": "Yes or No - does the bylaw have sections restricting excessive barking or noise from dogs?",
  "exempt_barking": "Yes if LGDs/working dogs are specifically exempt from barking/noise restrictions, No if not exempt, N/A if no barking restrictions exist",
  "dog_limit": "The general dog limit per household AND any exemptions for farms or agricultural properties",
  "progress_label": "COMPLETE - FARM FRIENDLY if the bylaw contains specific provisions that are favourable to LGDs/working dogs/farm dogs (definitions, exemptions, agricultural provisions), or COMPLETE if it's a standard animal control bylaw with no farm-friendly LGD provisions, or NO BY-LAW IN PLACE if no bylaw exists",
  "notes": "Any important observations about the bylaw's treatment of LGDs, recent amendments, or farm-relevant sections. Please provide the URL where you found the bylaw."
}
```

## Output Format
Return your results as a single JSON array containing one object per municipality.

## Important Rules
- **Quote definitions EXACTLY** as written in the bylaw — do not paraphrase
- **Be thorough** — look through the ENTIRE document including schedules and appendices
- Return ONLY the JSON array, no other commentary
"""

def generate_prompts():
    audit = pd.read_csv(os.path.join(SIGNALS_DIR, 'lgd_audit_2026-04-29.csv'))
    
    # Process P2 (Broken Links)
    p2 = audit[audit['Audit Result'] == 'LINK BROKEN']
    batch_size = 10
    num_p2_batches = math.ceil(len(p2) / batch_size)
    print(f"Generating {num_p2_batches} P2 prompts for {len(p2)} municipalities...")
    
    for i in range(num_p2_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(p2))
        batch = p2.iloc[start_idx:end_idx]
        
        muni_lines = []
        for idx, row in batch.iterrows():
            muni_lines.append(f"{len(muni_lines)+1}. {row['Municipality']} ({row['County']})")
        
        prompt = PROMPT_TEMPLATE.replace("{municipality_list}", "\n".join(muni_lines))
        prompt = prompt.replace("{phase}", "P2 (Broken Links)")
        prompt = prompt.replace("{batch_num}", str(i+1))
        
        out_path = os.path.join(SIGNALS_DIR, f"gemini_prompt_p2_batch_{i+1}.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"  Saved P2 Batch {i+1} -> {out_path}")

    # Process P3 (Needs Review)
    p3 = audit[audit['Audit Result'] == 'NEEDS REVIEW']
    num_p3_batches = math.ceil(len(p3) / batch_size)
    print(f"\nGenerating {num_p3_batches} P3 prompts for {len(p3)} municipalities...")
    
    for i in range(num_p3_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(p3))
        batch = p3.iloc[start_idx:end_idx]
        
        muni_lines = []
        for idx, row in batch.iterrows():
            muni_lines.append(f"{len(muni_lines)+1}. {row['Municipality']} ({row['County']})")
        
        prompt = PROMPT_TEMPLATE.replace("{municipality_list}", "\n".join(muni_lines))
        prompt = prompt.replace("{phase}", "P3 (Needs Review)")
        prompt = prompt.replace("{batch_num}", str(i+1))
        
        out_path = os.path.join(SIGNALS_DIR, f"gemini_prompt_p3_batch_{i+1}.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"  Saved P3 Batch {i+1} -> {out_path}")

if __name__ == "__main__":
    generate_prompts()
