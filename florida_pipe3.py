import csv
import glob
import os
from datetime import datetime

# ── ANSI COLORS ──────────────────────────────────────────
# Added M (Magenta) to fix the "Undefined Variable" error
G = "\033[92m"  # Green
Y = "\033[93m"  # Yellow
R = "\033[91m"  # Red
C = "\033[96m"  # Cyan
M = "\033[95m"  # Magenta
W = "\033[97m"  # White
RST = "\033[0m" # Reset

def bold(s): return f"\033[1m{s}{RST}"
def dim(s):  return f"\033[2m{s}{RST}"

def extract_targeted_leads():
    # 1. Find the newest evaluated file from Stage 3
    files = sorted(glob.glob("final_evaluated_leads_*.csv"), reverse=True)
    
    if not files:
        print(f"\n{R}Error: No 'final_evaluated_leads_*.csv' files found.{RST}")
        print(f"{dim('Make sure you ran the Stage 3 HTML analysis script first.')}")
        return
    
    input_file = files[0]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"outreach_priorities_{ts}.csv"

    filtered_leads = []
    
    # Counters for the summary report
    counts = {
        "Insecure": 0, 
        "Old_Copyright": 0, 
        "Fetch_Fail": 0
    }

    print(f"\n{bold(C+'PROCESSING OUTREACH PRIORITIES')}")
    print(f"{dim('Reading: ' + input_file)}")

    try:
        with open(input_file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Extract the issues string generated in Stage 3
                issues = row.get('tech_issues', '')
                
                # Logic for our three primary sales hooks
                # 1. Security (Not Secure/No SSL)
                is_ssl = "Not Secure" in issues or "No SSL" in issues
                
                # 2. Relevance (Old Copyright date or Aging site)
                is_copy = "Copyright" in issues or "Aging Site" in issues
                
                # 3. Accessibility (Site timed out or couldn't be read)
                is_fail = "Fetch Failed" in issues or "Could not retrieve" in issues

                # If any of these criteria are met, add to our priority list
                if is_ssl or is_copy or is_fail:
                    # Update counters for the summary (a lead can count for multiple)
                    if is_ssl: counts["Insecure"] += 1
                    if is_copy: counts["Old_Copyright"] += 1
                    if is_fail: counts["Fetch_Fail"] += 1
                    
                    filtered_leads.append(row)

    except Exception as e:
        print(f"{R}Failed to read file: {e}{RST}")
        return

    if not filtered_leads:
        print(f"{Y}No leads found matching your priority criteria.{RST}")
        return

    # 2. Save to a new focused CSV
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            # Use the fieldnames from the first lead found
            writer = csv.DictWriter(f, fieldnames=filtered_leads[0].keys())
            writer.writeheader()
            writer.writerows(filtered_leads)
    except Exception as e:
        print(f"{R}Error saving output file: {e}{RST}")
        return

    # ── SUMMARY REPORT ───────────────────────────────────────
    print("═" * 60)
    print(f"{bold(G+'TARGETED OUTREACH FILE CREATED')}")
    print("═" * 60)
    print(f"  {R}✘ Security Warnings:    {counts['Insecure']}{RST}")
    print(f"  {Y}⚠ Outdated Copyright:   {counts['Old_Copyright']}{RST}")
    print(f"  {M}⚑ Fetch/Load Failures:  {counts['Fetch_Fail']}{RST}")
    print("═" * 60)
    print(f"Total Unique Leads: {bold(W+str(len(filtered_leads)))}{RST}")
    print(f"File Saved As:      {bold(C+output_file)}{RST}")
    print("═" * 60 + "\n")

if __name__ == '__main__':
    extract_targeted_leads()