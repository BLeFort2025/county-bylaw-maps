# Scaling the Intelligence Engine: Adding New Bylaws & Keywords

The V3 Intelligence Scanner was specifically designed to be highly modular. You **do not** need to edit the complex web-spidering or AI code to track new issues in the future. The entire system is governed by a single configuration dictionary.

Follow these steps to track new bylaws (e.g., "Wind Turbines" or "Battery Storage") across all 444 municipalities.

## Step 1: Open the Shared Configuration File
1. Navigate to your project folder: `county-bylaw-maps`
2. Open the file named `shared_config.py` in Notepad or any code editor.

## Step 2: Edit the `KEYWORD_CONFIG` Dictionary
At the top of `shared_config.py`, you will see a dictionary called `KEYWORD_CONFIG`. This acts as the "brain" for both the Overnight AI Scanner and the Streamlit app.

It looks like this:
```python
KEYWORD_CONFIG = {
    "DC": [
        "Development Charge",
        "Development Charges Act",
        "DC Bylaw"
    ],
    "TREES": [
        "Tree Clearing",
        "Forest Conservation",
        "Tree Canopy"
    ]
}
```

To add a new issue, simply add a new Category Code and a list of trigger words below the existing ones. Make sure to use quotes and commas exactly as shown.

**Example: Adding "Battery Storage"**
```python
KEYWORD_CONFIG = {
    ... (existing categories) ...
    
    "BATTERY": [
        "Battery Energy Storage",
        "BESS",
        "Energy Storage System",
    ]
}
```

## Step 3: That's It! The System Handles the Rest
Because the architecture is fully dynamic, adding a new category to that single dictionary automatically triggers a massive chain reaction across your entire system:

1. **The Spider:** When the overnight `scanner_v3_spider.py` script runs tonight, it will automatically incorporate those new `"BATTERY"` keywords into its local speed-reading algorithm.
2. **The Gemini AI:** When the spider passes a "BATTERY" hit to Google Gemini, the code dynamically injects the new category name into the AI's prompt. *("Determine if this is a genuine policy action regarding our BATTERY bylaw category...")*. The AI will instantly understand the new context and filter out noise.
3. **The Database:** The `scanner_signals` database table is category-agnostic. It will seamlessly accept the new "BATTERY" signal and AI summary without needing structural updates.
4. **The Streamlit Dashboard:** The "Historical Intelligence Database" tab dynamically reads the database. Tomorrow morning, "BATTERY" will automatically appear as a new clickable dropdown filter on your live website for all OFA members.

### Note on Core Database Architecture
While the *Scanner* will instantly track and notify you about new keywords with zero extra work, if you eventually decide to actively audit and permanently track that bylaw's exact expiry dates across all 444 municipalities in your official database, you will still need to add a dedicated `details_battery` table to your `db_schema.py` and update your Streamlit map dashboard appropriately.
