import asyncio
import aiohttp
import csv
import re
import sys
import time
from datetime import datetime
from collections import defaultdict

# ── ANSI COLORS ──────────────────────────────────────────
G, Y, R, C, W, RST = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[97m", "\033[0m"
def bold(s): return f"\033[1m{s}{RST}"
def dim(s):  return f"\033[2m{s}{RST}"

# ── CONFIGURATION ────────────────────────────────────────
HTML_WORKERS = 50   # Keep between 40-60 to avoid OS socket hangs
HTML_TIMEOUT = 10   # Total seconds per site
MAX_READ_SIZE = 1024 * 100  # 100KB is plenty for SEO/Meta/Tech analysis

def extract_tech_score(html: str, url: str) -> tuple[int, list]:
    issues = []
    score = 10
    
    # 1. SSL Check
    if not url.lower().startswith('https://'):
        score -= 2
        issues.append("No SSL")

    # 2. Copyright Year (Updated for 2026)
    matches = re.findall(r'©\s*(\d{4})|copyright\s*(\d{4})', html, re.IGNORECASE)
    years = [int(y) for pair in matches for y in pair if y]
    if years:
        oldest = min(years)
        age = 2026 - oldest
        if age >= 8:
            score -= 2
            issues.append(f"Outdated Copyright ({oldest})")
        elif age >= 5:
            score -= 1
            issues.append(f"Aging Site ({oldest})")

    # 3. Mobile/SEO Check
    if not re.search(r'<meta[^>]+viewport', html, re.IGNORECASE):
        score -= 2
        issues.append("Not Mobile Friendly (No Viewport)")
    if not re.search(r'<title>', html, re.IGNORECASE):
        score -= 1
        issues.append("Missing Title Tag")

    # 4. Contact Presence
    has_phone = bool(re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', html))
    has_email = bool(re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html))
    if not (has_phone or has_email):
        score -= 2
        issues.append("No Contact Info Found")

    return max(score, 0), issues

async def fetch_and_analyze(session, sem, lead, progress):
    url = (lead.get('redirect_url') or lead.get('website', '')).strip()
    if not url.startswith('http'):
        url = 'http://' + url

    async with sem:
        try:
            async with session.get(url, ssl=False) as resp:
                # We only read the first chunk to prevent hanging on huge files
                content = await resp.content.read(MAX_READ_SIZE)
                html = content.decode('utf-8', errors='ignore')
                
                score, issues = extract_tech_score(html, url)
                lead.update({
                    'tech_score': score,
                    'tech_issues': ' | '.join(issues),
                    'pipeline_stage': 'weak_site' if score <= 5 else 'decent_site'
                })
        except Exception:
            lead.update({
                'tech_score': 3,
                'tech_issues': 'Fetch Failed (Timeout/Blocked)',
                'pipeline_stage': 'weak_site'
            })

    progress['done'] += 1
    pct = round(progress['done'] / progress['total'] * 100)
    print(f"  {G}Analyzing:{RST} {pct}% [{progress['done']}/{progress['total']}]", end='\r')
    return lead

async def main():
    input_file = "pipeline_s1s2_alive_20260512_152903.csv" # Your specific file
    
    try:
        with open(input_file, newline='', encoding='utf-8') as f:
            leads = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"{R}Error: {input_file} not found.{RST}")
        return

    print(f"\n{bold(C+'STAGE 3: HTML DEEP EVALUATION')}")
    print(f"{dim('Processing ' + str(len(leads)) + ' alive leads...')}\n")

    sem = asyncio.Semaphore(HTML_WORKERS)
    progress = {'done': 0, 'total': len(leads)}
    
    # TCPConnector helps manage the underlying pool of connections
    connector = aiohttp.TCPConnector(limit=HTML_WORKERS, use_dns_cache=True, ssl=False)
    timeout = aiohttp.ClientTimeout(total=HTML_TIMEOUT)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as session:
        tasks = [fetch_and_analyze(session, sem, l, progress) for l in leads]
        results = await asyncio.gather(*tasks)

    print("\n\n" + bold(G + "ANALYSIS COMPLETE"))
    
    # Save Output
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"final_evaluated_leads_{ts}.csv"
    
    # Ensure priority_score is calculated for sorting
    for l in results:
        # Simple formula: Lower tech score + higher reviews = High Priority
        reviews = int(l.get('review_count') or 0)
        t_score = int(l.get('tech_score') or 10)
        l['priority_score'] = (10 - t_score) * 5 + (min(reviews, 100) / 2)

    results.sort(key=lambda x: x['priority_score'], reverse=True)

    with open(out_name, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved {len(results)} evaluated leads to: {bold(out_name)}")

if __name__ == '__main__':
    asyncio.run(main())