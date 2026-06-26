import pandas as pd

# 1. Load your final website technical target list
input_file = 'FINAL_WEBSITE_TECHNICAL_TARGET_LIST.csv'
print(f"Loading {input_file}...")
df = pd.read_csv(input_file)

# 2. Define the translation function for your cold calling pitches
def get_pitch_explanation(status):
    status = str(status).strip().lower()
    
    if 'connection_error' in status or 'dead' in status:
        return ("CRITICAL: Website is completely offline. Looks like the business went under. "
                "Customers get a blank error screen and leave instantly to call competitors.")
                
    elif 'timeout' in status:
        return ("SLOW: Website takes way too long to respond. It timed out. "
                "Impatient buyers look elsewhere within 3 seconds, killing your marketing dollar.")
                
    elif 'ssl_error' in status:
        return ("SECURITY RISK: Google/Safari blocks traffic with a terrifying red warning screen "
                "saying 'Connection is Not Private'. Scares away 90% of visitors who think they'll get hacked.")
                
    elif '404' in status:
        return ("BROKEN LINK (404): The web link points to a page that doesn't exist anymore. "
                "Your digital front door is locked; customers can't see your contact info or forms.")
                
    elif status in ['500', '502', '503']:
        return (f"SERVER CRASH ({status}): Server is temporarily broken, overloaded, or crashing. "
                f"It's the digital equivalent of putting a 'Temporarily Closed' sign on your shop front.")
                
    else:
        return (f"TECHNICAL ERROR ({status}): Background system glitch that is stopping pages from loading right. "
                f"Destroys professional credibility and drives online search traffic down.")

# 3. Add the brand new pitch column right next to the HTTP status
print("Generating plain-English pitch explanations for cold calling...")
df['pitch_explanation'] = df['http_status'].apply(get_pitch_explanation)

# 4. Physically group the spreadsheet rows by City and then by Industry
print("Grouping data by city and industry...")
df = df.sort_values(by=['city', 'industry'], ascending=[True, True])

# 5. Reorder columns to put the pitch explanation right next to the status for fast reading
all_cols = list(df.columns)
if 'http_status' in all_cols and 'pitch_explanation' in all_cols:
    status_idx = all_cols.index('http_status')
    all_cols.remove('pitch_explanation')
    all_cols.insert(status_idx + 1, 'pitch_explanation')
    df = df[all_cols]

# 6. Save out the new complete lead sheet
output_file = 'final_website_technical_pitch_list.csv'
df.to_csv(output_file, index=False)

print(f"Done! The new lead sheet with cold calling pitches has been saved as {output_file}.")