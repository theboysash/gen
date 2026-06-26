import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import playwright_stealth
import os
import re

# ── CONFIGURATION ───────────────────────────────────────
INPUT_CSV = "pipeline_s1s2_alive_20260512_152903.csv"
START_INDEX = 2000         # Starting after the first 2000
LEAD_LIMIT = 1500          # Taking the final 1500 (up to 3500)
TARGET_FOLDER = "temp_screens3"
CONCURRENT_WORKERS = 15    # Full speed for the home stretch

# ── FILENAME LOGIC ──────────────────────────────────────
def get_safe_path(url):
    if not url or pd.isna(url): return None
    clean = str(url).replace('https://', '').replace('http://', '').replace('www.', '').strip().rstrip('/')
    clean = re.sub(r'[^a-zA-Z0-9]', '_', clean).lower()
    if not clean: return None
    return os.path.join(os.getcwd(), TARGET_FOLDER, f"{clean[:50]}.png")

async def capture_task(semaphore, browser, lead, pbar):
    async with semaphore:
        raw_url = str(lead.get('website', '')).strip()
        if not raw_url or raw_url == 'nan': 
            pbar['count'] += 1
            return

        target_url = raw_url if raw_url.startswith('http') else 'https://' + raw_url
        save_path = get_safe_path(target_url)

        # Skip if file already exists
        if os.path.exists(save_path):
            pbar['count'] += 1
            return

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            try: await playwright_stealth.stealth_async(page)
            except: pass

            # 25s timeout to catch slower servers
            response = await page.goto(target_url, timeout=25000, wait_until="load")
            
            if response:
                await asyncio.sleep(2.5) 
                await page.screenshot(path=save_path)
        except Exception:
            pass 
        finally:
            await context.close()
            pbar['count'] += 1
            print(f"Final Sprint: {pbar['count']}/{pbar['total']} leads in {TARGET_FOLDER}", end='\r')

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found.")
        return

    # Slice the dataframe for the 2000-3500 range
    df = pd.read_csv(INPUT_CSV)
    leads = df.iloc[START_INDEX : START_INDEX + LEAD_LIMIT].to_dict('records')
    
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
    
    print(f"🏁 Starting Final Phase: Index {START_INDEX} to {START_INDEX + len(leads)}...")
    print(f"Saving to: {TARGET_FOLDER}")

    semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
    pbar = {'count': 0, 'total': len(leads)}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [capture_task(semaphore, browser, lead, pbar) for lead in leads]
        await asyncio.gather(*tasks)
        await browser.close()
    
    print(f"\n✅ FULL LIST COMPLETE. Folder '{TARGET_FOLDER}' is filled.")

if __name__ == "__main__":
    asyncio.run(main())