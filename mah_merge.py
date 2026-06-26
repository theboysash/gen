import pandas as pd

# 1. Define the correct file names (assumes .csv extension)
master_file = 'final_evaluated_leads_20260512_194042.csv'
target_files = {
    'FINAL_NO_WEBSITE_TARGET_LIST': 'FINAL_NO_WEBSITE_TARGET_LIST.csv',
    'FINAL_WEBSITE_TECHNICAL_TARGET_LIST': 'FINAL_WEBSITE_TECHNICAL_TARGET_LIST.csv',
    'FINAL_TARGET_REVAMP_LIST': 'FINAL_TARGET_REVAMP_LIST.csv'
}

print(f"Loading master CSV: {master_file}...")
master_df = pd.read_csv(master_file)

# Create standardized matching keys in master to avoid case/space mismatches
master_df['match_name'] = master_df['name'].astype(str).str.strip().str.lower()
master_df['match_phone'] = master_df['phone'].astype(str).str.strip().str.lower()
master_df['match_city'] = master_df['city'].astype(str).str.strip().str.lower()

# 2. Process and extract keys from each target list
target_list_dfs = []

for list_name, file_path in target_files.items():
    print(f"Loading and processing {list_name}...")
    try:
        df = pd.read_csv(file_path)
        
        # Standardize matching keys for this target list
        df['match_name'] = df['name'].astype(str).str.strip().str.lower()
        df['match_phone'] = df['phone'].astype(str).str.strip().str.lower()
        df['match_city'] = df['city'].astype(str).str.strip().str.lower()
        
        # We only need the keys to find matches in the master, plus our new source tracker
        df_keys = df[['match_name', 'match_phone', 'match_city']].copy()
        df_keys['source_csv'] = list_name
        
        target_list_dfs.append(df_keys)
    except FileNotFoundError:
        print(f"Warning: File {file_path} not found. Skipping.")

# 3. Combine all target keys into a single dataset
combined_targets = pd.concat(target_list_dfs, ignore_index=True)

# 4. Consolidate rows that appear in multiple lists
print("Consolidating duplicate entries across target lists...")
combined_targets_grouped = (
    combined_targets.groupby(['match_name', 'match_phone', 'match_city'])['source_csv']
    .apply(lambda x: ', '.join(x.unique()))
    .reset_index()
)

# 5. Merge with the master DataFrame to extract all the juicy information
print("Merging with master data to extract all rich details...")
merged_df = pd.merge(
    master_df, 
    combined_targets_grouped, 
    on=['match_name', 'match_phone', 'match_city'], 
    how='inner'
)

# 6. Clean up temporary matching columns
merged_df = merged_df.drop(columns=['match_name', 'match_phone', 'match_city'])

# 7. Move 'source_csv' to be the very first column for easy viewing
cols = ['source_csv'] + [col for col in merged_df.columns if col != 'source_csv']
merged_df = merged_df[cols]

# 8. Export the enriched data to a new CSV file
output_file = 'final_evaluated_filtered_leads.csv'
merged_df.to_csv(output_file, index=False)

print(f"\nSuccess! Saved the final file as '{output_file}' with {len(merged_df)} matching entries.")