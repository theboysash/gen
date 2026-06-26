import pandas as pd
import os

# ── CONFIGURATION ───────────────────────────────────────
INPUT_FILE = "florida_with_website.csv"
OUTPUT_FILE = "FINAL_WEBSITE_TECHNICAL_TARGET_LIST.csv"

def finalize_technical_website_list():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: {INPUT_FILE} not found!")
        return

    # 1. Load the "With Website" batch
    df = pd.read_csv(INPUT_FILE)

    # 2. Select the core outreach columns + Technical fields
    cols_to_keep = [
        'city', 'area', 'industry', 'name', 'phone', 
        'website', 'rating', 'review_count', 'address',
        'http_status', 'fake_tier' # The technical "Pain Points"
    ]
    
    df = df[[c for c in cols_to_keep if c in df.columns]]

    # 3. Create sorting helper: Has Phone (1) or No Phone (0)
    df['has_phone'] = df['phone'].notna() & (df['phone'].astype(str).str.strip() != '')

    # 4. Multi-level Sort Strategy:
    #   - Phone numbers at the top (Actionable)
    #   - City (Local grouping)
    #   - HTTP Status (Find the broken 404s/500s first)
    #   - Fake Tier (Target the lowest quality 'Tier 3' sites first)
    #   - Review Count (Highest potential first)
    
    df = df.sort_values(
        by=['has_phone', 'city', 'http_status', 'fake_tier', 'review_count'], 
        ascending=[False, True, False, False, False] 
    )

    # 5. Clean up helper
    df = df.drop(columns=['has_phone'])

    # 6. Export
    df.to_csv(OUTPUT_FILE, index=False)

    print("\n" + "═"*50)
    print(f"🚀 TECHNICAL TARGET LIST READY: {OUTPUT_FILE}")
    print(f"📈 Total Leads: {len(df)}")
    print(f"🔍 Sorting: Phone > City > Broken Status > Tier > Reviews")
    print("═"*50)

if __name__ == "__main__":
    finalize_technical_website_list()