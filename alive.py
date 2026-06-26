import asyncio
import aiohttp
import csv
import re
import sys
import glob
import time
from datetime import datetime
from urllib.parse import urlparse

# ── ANSI colours ─────────────────────────────────────────
R  = "\033[91m"
G  = "\033[92m"
Y  = "\033[93m"
B  = "\033[94m"
M  = "\033[95m"
C  = "\033[96m"
W  = "\033[97m"
DIM= "\033[2m"
BLD= "\033[1m"
RST= "\033[0m"

def red(s):     return f"{R}{s}{RST}"
def green(s):   return f"{G}{s}{RST}"
def yellow(s):  return f"{Y}{s}{RST}"
def blue(s):    return f"{B}{s}{RST}"
def magenta(s): return f"{M}{s}{RST}"
def cyan(s):    return f"{C}{s}{RST}"
def white(s):   return f"{W}{s}{RST}"
def bold(s):    return f"{BLD}{s}{RST}"
def dim(s):     return f"{DIM}{s}{RST}"

def bar(value, max_val, width=30, fill="█", empty="░"):
    filled = round((value / max_val) * width) if max_val else 0
    return f"{G}{fill * filled}{DIM}{empty * (width - filled)}{RST}"

# ── Config ────────────────────────────────────────────────
HEAD_WORKERS = 250   # HEAD request concurrency
GET_WORKERS  = 200   # GET fallback concurrency
HEAD_TIMEOUT = 5     # seconds
GET_TIMEOUT  = 8     # seconds (slightly more lenient)

# ── Fake website patterns ─────────────────────────────────
FAKE_PATTERNS = [
    'facebook.com', 'fb.com', 'fb.me', 'twitter.com',
    'instagram.com',
    'wixsite.com', 'wix.com',
    'weebly.com',
    'my.canva.site', 'canva.site',
    'business.site',
    'squarespace.com',
    'linktr.ee', 'linktree.com',
    'yellowpages.com',
    'yelp.com',
    'tripadvisor.com',
    'thumbtack.com',
    'angieslist.com', 'angi.com',
    'homeadvisor.com',
    'houzz.com',
    'linkedin.com',
    'nextdoor.com',
    'google.com/maps',
    'maps.google.com',
    'cylex', 'hotfrog',
    'manta.com', 'bizapedia.com',
    'chamberofcommerce.com',
    'bark.com', 'networx.com',
    'mysite.com',
    'godaddysites.com',
    'wordpress.com',
    'blogspot.com',
    'sites.google.com',
]

def classify_url(url: str) -> str:
    if not url or url.strip() == '':
        return 'none'
    url_lower = url.lower()
    for pattern in FAKE_PATTERNS:
        if pattern in url_lower:
            return 'fake'
    return 'real'

def check_ssl_from_url(url: str) -> bool:
    return url.lower().startswith('https://')


# ── Stage 1a: HEAD requests ───────────────────────────────

async def head_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    lead: dict,
    progress: dict,
) -> dict:
    url = lead.get('website', '').strip()
    result = {
        **lead,
        'http_status':   None,
        'redirect_url':  None,
        'response_ms':   None,
        'alive':         False,
        'needs_get':     False,
        'method_used':   'head',
    }

    if not url:
        progress['done'] += 1
        return result

    async with semaphore:
        start = time.time()
        try:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=HEAD_TIMEOUT),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                elapsed = round((time.time() - start) * 1000)
                final_url = str(resp.url)
                result['http_status']  = resp.status
                result['redirect_url'] = final_url if final_url != url else None
                result['response_ms']  = elapsed
                result['alive']        = resp.status < 400

                # Some servers return 405 (method not allowed) for HEAD
                # or 403 that might be HEAD-specific — flag for GET retry
                if resp.status in (405, 501, 403):
                    result['needs_get'] = True

        except asyncio.TimeoutError:
            result['http_status'] = 'timeout'
            result['needs_get']   = True   # retry with GET
        except aiohttp.ClientSSLError:
            result['http_status'] = 'ssl_error'
            result['alive']       = True   # site exists, just bad SSL
        except aiohttp.ClientConnectorError:
            result['http_status'] = 'connection_error'
        except Exception:
            result['http_status'] = 'error'
            result['needs_get']   = True

    progress['done'] += 1
    if progress['done'] % 500 == 0 or progress['done'] == progress['total']:
        pct    = round(progress['done'] / progress['total'] * 100)
        filled = round(pct / 100 * 40)
        b = f"{G}{'█'*filled}{DIM}{'░'*(40-filled)}{RST}"
        print(f"  {b} {bold(str(pct)+'%')} {dim(str(progress['done'])+'/'+str(progress['total']))}", end='\r')

    return result


# ── Stage 1b: GET fallback ────────────────────────────────

async def get_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    lead: dict,
    progress: dict,
) -> dict:
    url = lead.get('website', '').strip()

    async with semaphore:
        start = time.time()
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=GET_TIMEOUT),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                elapsed    = round((time.time() - start) * 1000)
                final_url  = str(resp.url)
                lead['http_status']  = resp.status
                lead['redirect_url'] = final_url if final_url != url else None
                lead['response_ms']  = elapsed
                lead['alive']        = resp.status < 400
                lead['method_used']  = 'get'
                lead['needs_get']    = False

        except asyncio.TimeoutError:
            lead['http_status'] = 'dead'
            lead['alive']       = False
            lead['method_used'] = 'get'
        except aiohttp.ClientSSLError:
            lead['http_status'] = 'ssl_error'
            lead['alive']       = True
            lead['method_used'] = 'get'
        except Exception:
            lead['http_status'] = 'dead'
            lead['alive']       = False
            lead['method_used'] = 'get'

    progress['done'] += 1
    if progress['done'] % 250 == 0 or progress['done'] == progress['total']:
        pct    = round(progress['done'] / progress['total'] * 100)
        filled = round(pct / 100 * 40)
        b = f"{G}{'█'*filled}{DIM}{'░'*(40-filled)}{RST}"
        print(f"  {b} {bold(str(pct)+'%')} {dim(str(progress['done'])+'/'+str(progress['total']))}", end='\r')

    return lead


async def run_head_stage(leads: list) -> list:
    semaphore = asyncio.Semaphore(HEAD_WORKERS)
    progress  = {'done': 0, 'total': len(leads)}
    connector = aiohttp.TCPConnector(limit=300, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        tasks   = [head_one(session, semaphore, lead, progress) for lead in leads]
        results = await asyncio.gather(*tasks)
    print()
    return list(results)


async def run_get_stage(leads: list) -> list:
    semaphore = asyncio.Semaphore(GET_WORKERS)
    progress  = {'done': 0, 'total': len(leads)}
    connector = aiohttp.TCPConnector(limit=300, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        tasks   = [get_one(session, semaphore, lead, progress) for lead in leads]
        results = await asyncio.gather(*tasks)
    print()
    return list(results)


# ── Stage 2: URL classification ───────────────────────────

def classify_leads(leads: list) -> list:
    for lead in leads:
        url       = lead.get('website', '')
        final_url = lead.get('redirect_url') or url
        lead['url_type'] = classify_url(final_url)
        lead['has_ssl']  = check_ssl_from_url(final_url or url)
        lead['final_url']= final_url
    return leads


# ── Stage 3: Priority scoring ─────────────────────────────

def score_lead(lead: dict) -> int:
    score      = 0
    url_type   = lead.get('url_type', 'none')
    status     = lead.get('http_status')
    has_ssl    = lead.get('has_ssl', False)
    reviews    = int(lead.get('review_count') or 0)
    has_website= lead.get('has_website', 'No')

    # Base score
    if url_type == 'none' or has_website == 'No':
        score += 100
    elif isinstance(status, int) and status >= 400:
        score += 90    # dead site
    elif status == 'dead':
        score += 90
    elif status == 'ssl_error':
        score += 85
    elif url_type == 'fake':
        score += 80
    elif status == 'connection_error':
        score += 75
    else:
        score += 20    # real, alive site

    # SSL penalty for real sites
    if url_type == 'real' and not has_ssl:
        score += 15

    # Review bonus — established business with no/bad site = best lead
    if reviews >= 200:   score += 20
    elif reviews >= 100: score += 15
    elif reviews >= 50:  score += 10
    elif reviews >= 20:  score += 7
    elif reviews >= 10:  score += 3

    # Slow response penalty
    ms = lead.get('response_ms')
    if isinstance(ms, int):
        if ms > 5000: score += 8
        elif ms > 3000: score += 4

    return min(score, 100)


# ── Display helpers ───────────────────────────────────────

def status_display(lead: dict) -> str:
    status   = lead.get('http_status')
    url_type = lead.get('url_type', 'real')
    ht       = lead.get('has_website', 'No')

    if ht == 'No' or url_type == 'none':
        return red("NO WEBSITE")
    if url_type == 'fake':
        return yellow("FAKE SITE ")
    if status == 'ssl_error':
        return yellow("SSL ERROR ")
    if status in ('dead', 'connection_error'):
        return red("DEAD      ")
    if status == 'timeout':
        return magenta("TIMEOUT   ")
    if isinstance(status, int):
        if status == 200: return green("200 OK    ")
        if status in (301, 302): return cyan(f"{status} REDIR  ")
        if status >= 500: return red(f"{status} ERROR ")
        if status >= 400: return red(f"{status} ERROR ")
        return dim(f"{status}       ")
    return dim(str(status)[:10].ljust(10))

def priority_display(score: int) -> str:
    if score >= 90: return f"{R}{'█'*5} P{score:>3}{RST}"
    if score >= 75: return f"{Y}{'█'*4} P{score:>3}{RST}"
    if score >= 50: return f"{M}{'█'*3} P{score:>3}{RST}"
    if score >= 30: return f"{B}{'█'*2} P{score:>3}{RST}"
    return f"{DIM}{'█'*1} P{score:>3}{RST}"


# ── Main ──────────────────────────────────────────────────

def main():
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1]
    else:
        csvs = sorted(glob.glob("florida_raw_*.csv"), reverse=True)
        if not csvs:
            print(red("No florida_raw_*.csv found."))
            sys.exit(1)
        csv_path = csvs[0]

    print()
    print(f"{BLD}{'═'*70}{RST}")
    print(f"  {bold(cyan('LeadGen Florida — Pipeline Triage v2'))}")
    print(f"  {dim('HEAD → GET fallback → URL classify → Score')}")
    print(f"{'═'*70}{RST}")
    print(f"  {dim('File: ' + csv_path)}")
    print(f"  {dim('Run:  ' + datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print(f"  {dim(f'Workers: HEAD={HEAD_WORKERS}  GET={GET_WORKERS}')}")
    print()

    with open(csv_path, newline='', encoding='utf-8') as f:
        all_leads = list(csv.DictReader(f))

    total   = len(all_leads)
    no_url  = [l for l in all_leads if not l.get('website', '').strip()]
    has_url = [l for l in all_leads if l.get('website', '').strip()]

    print(f"  {bold(white(f'{total:,}'))} businesses loaded")
    print(f"  {green(str(len(no_url)))} have no URL at all")
    print(f"  {yellow(str(len(has_url)))} have a URL to check")
    print()

    # ── Stage 1a: HEAD ────────────────────────────────────
    print(f"{bold('STAGE 1a')} — HEAD requests ({bold(str(HEAD_WORKERS))} workers)")
    print(f"{'─'*70}")
    t1a = time.time()
    head_results = asyncio.run(run_head_stage(has_url))
    e1a = round(time.time() - t1a, 1)
    print(f"  {green('✓')} Completed in {bold(str(e1a)+'s')}")

    needs_get = [l for l in head_results if l.get('needs_get')]
    confirmed = [l for l in head_results if not l.get('needs_get')]

    alive_head = [l for l in confirmed if l.get('alive')]
    dead_head  = [l for l in confirmed if not l.get('alive')]

    print(f"  {green(str(len(alive_head)))} confirmed alive from HEAD")
    print(f"  {red(str(len(dead_head)))} confirmed dead from HEAD")
    print(f"  {yellow(str(len(needs_get)))} need GET fallback (timeouts/405s/403s)")
    print()

    # ── Stage 1b: GET fallback ────────────────────────────
    print(f"{bold('STAGE 1b')} — GET fallback ({bold(str(GET_WORKERS))} workers, {bold(str(len(needs_get)))} sites)")
    print(f"{'─'*70}")
    t1b = time.time()
    get_results = asyncio.run(run_get_stage(needs_get))
    e1b = round(time.time() - t1b, 1)
    print(f"  {green('✓')} Completed in {bold(str(e1b)+'s')}")

    alive_get = [l for l in get_results if l.get('alive')]
    dead_get  = [l for l in get_results if not l.get('alive')]
    print(f"  {green(str(len(alive_get)))} recovered as alive via GET")
    print(f"  {red(str(len(dead_get)))} confirmed dead after GET fallback")
    print()

    # Merge all results
    all_checked = confirmed + get_results

    # Status breakdown
    print(f"  {bold('Final HTTP Status Breakdown:')}")
    status_counts = {}
    for l in all_checked:
        s = str(l.get('http_status', 'unknown'))
        status_counts[s] = status_counts.get(s, 0) + 1
    max_sc = max(status_counts.values()) if status_counts else 1
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1])[:12]:
        b   = bar(count, max_sc, width=20)
        col = green if status == '200' else red if status in ('dead','connection_error','ssl_error') or (status.isdigit() and int(status) >= 400) else cyan
        print(f"    {col(str(status).ljust(20))} {b} {bold(str(count))}")

    total_alive = len([l for l in all_checked if l.get('alive')])
    total_dead  = len([l for l in all_checked if not l.get('alive')])
    print()
    print(f"  {green(bold(str(total_alive)))} total alive  {red(bold(str(total_dead)))} total dead")
    print()

    # ── Stage 2: URL classification ───────────────────────
    print(f"{bold('STAGE 2')} — URL pattern classification")
    print(f"{'─'*70}")
    t2 = time.time()
    classified = classify_leads(all_checked)

    for l in no_url:
        l.update({
            'url_type': 'none', 'has_ssl': False, 'final_url': '',
            'http_status': None, 'alive': False, 'response_ms': None,
            'redirect_url': None, 'needs_get': False, 'method_used': 'none',
        })

    e2 = round((time.time() - t2) * 1000)

    fake_sites = [l for l in classified if l.get('url_type') == 'fake']
    real_sites = [l for l in classified if l.get('url_type') == 'real']
    no_ssl     = [l for l in real_sites if not l.get('has_ssl')]

    print(f"  {green('✓')} Completed in {bold(str(e2)+'ms')}")
    print()
    print(f"  {red(bold(str(len(no_url))))}   no website at all")
    print(f"  {yellow(bold(str(len(fake_sites))))}   fake websites")
    print(f"  {green(bold(str(len(real_sites))))}  real websites")
    print(f"  {yellow(bold(str(len(no_ssl))))}  real sites with no SSL")
    print()

    fake_by_type = {}
    for l in fake_sites:
        url = (l.get('final_url') or l.get('website', '')).lower()
        for pattern in FAKE_PATTERNS:
            if pattern in url:
                fake_by_type[pattern] = fake_by_type.get(pattern, 0) + 1
                break
    if fake_by_type:
        print(f"  {bold('Fake site breakdown:')}")
        max_f = max(fake_by_type.values())
        for pattern, count in sorted(fake_by_type.items(), key=lambda x: -x[1])[:10]:
            b = bar(count, max_f, width=20)
            print(f"    {yellow(pattern.ljust(28))} {b} {bold(str(count))}")
    print()

    # ── Stage 3: Scoring ──────────────────────────────────
    print(f"{bold('STAGE 3')} — Priority scoring")
    print(f"{'─'*70}")
    t3 = time.time()

    all_combined = no_url + classified
    for lead in all_combined:
        lead['priority_score'] = score_lead(lead)
    all_combined.sort(key=lambda x: x['priority_score'], reverse=True)

    e3 = round((time.time() - t3) * 1000)
    print(f"  {green('✓')} Scored {bold(str(len(all_combined)))} leads in {bold(str(e3)+'ms')}")
    print()

    p100 = [l for l in all_combined if l['priority_score'] == 100]
    p90  = [l for l in all_combined if 90 <= l['priority_score'] < 100]
    p75  = [l for l in all_combined if 75 <= l['priority_score'] < 90]
    p50  = [l for l in all_combined if 50 <= l['priority_score'] < 75]
    p30  = [l for l in all_combined if 30 <= l['priority_score'] < 50]
    plo  = [l for l in all_combined if l['priority_score'] < 30]
    max_p = max(len(p100), len(p90), len(p75), len(p50), len(p30), len(plo), 1)

    print(f"  {bold('Priority Score Distribution:')}")
    print(f"    {red('P100 (no website)'  .ljust(24))} {bar(len(p100),max_p,25)} {bold(red(str(len(p100))))}")
    print(f"    {red('P90-99 (dead/dying)'.ljust(24))} {bar(len(p90), max_p,25)} {bold(red(str(len(p90))))}")
    print(f"    {yellow('P75-89 (fake/ssl)'  .ljust(24))} {bar(len(p75), max_p,25)} {bold(yellow(str(len(p75))))}")
    print(f"    {magenta('P50-74 (medium)'    .ljust(24))} {bar(len(p50), max_p,25)} {bold(magenta(str(len(p50))))}")
    print(f"    {blue('P30-49 (low)'       .ljust(24))} {bar(len(p30), max_p,25)} {bold(blue(str(len(p30))))}")
    print(f"    {dim('P0-29 (skip)'       .ljust(24))} {bar(len(plo), max_p,25)} {bold(dim(str(len(plo))))}")
    print()

    # ── Top 30 preview ────────────────────────────────────
    print(f"{bold('TOP 30 LEADS')} — Sorted by priority score")
    print(f"{'─'*70}")
    print(f"  {dim('Priority   Status       Business                      City          Reviews')}")
    print(f"  {dim('─'*67)}")
    for lead in all_combined[:30]:
        name    = lead.get('name', 'Unknown')[:28].ljust(28)
        city    = lead.get('city', '')[:13].ljust(13)
        reviews = int(lead.get('review_count') or 0)
        rev_str = f"{reviews:>4}★" if reviews else dim("  no★")
        print(f"  {priority_display(lead['priority_score'])}  {status_display(lead)}  {white(name)}  {dim(city)}  {yellow(str(rev_str))}")
    print()

    # ── Deep queue breakdown ──────────────────────────────
    deep_queue = all_combined[:500]
    none_q = [l for l in deep_queue if l.get('url_type') == 'none']
    dead_q = [l for l in deep_queue if not l.get('alive') and l.get('website') and l.get('url_type') != 'none']
    fake_q = [l for l in deep_queue if l.get('url_type') == 'fake']
    real_q = [l for l in deep_queue if l.get('url_type') == 'real' and l.get('alive')]

    print(f"{bold('DEEP ANALYSIS QUEUE')} — Top 500 for Playwright + OpenAI")
    print(f"{'─'*70}")
    print(f"  {red(bold(str(len(none_q))))}  no website at all")
    print(f"  {red(bold(str(len(dead_q))))}  dead / unreachable sites")
    print(f"  {yellow(bold(str(len(fake_q))))}  fake websites (Facebook, Wix etc)")
    print(f"  {magenta(bold(str(len(real_q))))}  real but weak sites → Playwright scoring")
    print()

    # ── Summary ───────────────────────────────────────────
    total_time = round(e1a + e1b + (e2/1000) + (e3/1000), 1)
    print(f"{'═'*70}")
    print(f"  {bold(cyan('PIPELINE COMPLETE'))}")
    print(f"{'═'*70}")
    print(f"  Stage 1a HEAD ({HEAD_WORKERS} workers) : {green(str(e1a)+'s')}")
    print(f"  Stage 1b GET  ({GET_WORKERS} workers)  : {green(str(e1b)+'s')}")
    print(f"  Stage 2  URL classify          : {green(str(e2)+'ms')}")
    print(f"  Stage 3  Scoring               : {green(str(e3)+'ms')}")
    print(f"  {bold('Total')}                         : {bold(green(str(total_time)+'s'))}")
    print()
    print(f"  {bold(white(str(len(all_combined))))} leads scored and ranked")
    print(f"  {bold(red(str(len(deep_queue))))} queued for deep Playwright analysis")
    print(f"  {bold(green(str(len(all_combined)-len(deep_queue))))} deprioritised")
    print()

    # Save
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"florida_triaged_{ts}.csv"
    fields   = list(all_combined[0].keys()) if all_combined else []
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_combined)
    print(f"  {green('✓')} Saved: {bold(out_path)}")
    print()

if __name__ == '__main__':
    main()