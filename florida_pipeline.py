import asyncio
import aiohttp
import csv
import re
import sys
import glob
import time
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse

# ── ANSI colours ──────────────────────────────────────────
R   = "\033[91m"
G   = "\033[92m"
Y   = "\033[93m"
B   = "\033[94m"
M   = "\033[95m"
C   = "\033[96m"
W   = "\033[97m"
DIM = "\033[2m"
BLD = "\033[1m"
RST = "\033[0m"

def red(s):     return f"{R}{s}{RST}"
def green(s):   return f"{G}{s}{RST}"
def yellow(s):  return f"{Y}{s}{RST}"
def blue(s):    return f"{B}{s}{RST}"
def magenta(s): return f"{M}{s}{RST}"
def cyan(s):    return f"{C}{s}{RST}"
def white(s):   return f"{W}{s}{RST}"
def bold(s):    return f"{BLD}{s}{RST}"
def dim(s):     return f"{DIM}{s}{RST}"

def bar(value, max_val, width=28, color=G):
    filled = round((value / max_val) * width) if max_val else 0
    return f"{color}{'█'*filled}{DIM}{'░'*(width-filled)}{RST}"

def divider(w=70): print("─" * w)
def section(title):
    print()
    print("═" * 70)
    print(f"  {bold(cyan(title))}")
    print("═" * 70)

# ── Fake website patterns ─────────────────────────────────

# Tier A — highest priority (Google shut down / social profile as site)
FAKE_TIER_A = [
    'business.site',          # Google discontinued March 2026
    'facebook.com', 'fb.com', 'fb.me',
    'instagram.com',
    'linktr.ee', 'linktree.com',
    'beacons.ai',
    'bio.site',
    'tiktok.com',
    'youtube.com',
]

# Tier B — free subdomain builders (amateur / unfinished)
FAKE_TIER_B = [
    'wixsite.com', 'wix.com',
    'weebly.com',
    'wordpress.com',
    'site123.me',
    'webflow.io',
    'canva.site', 'my.canva.site',
    'godaddysites.com',
    'sites.google.com',
    'squarespace.com',
    'blogspot.com',
    'mystrikingly.com',
    'simplesite.com',
    'jimdo.com',
    '8b.io',
    'carrd.co',
]

# Tier C — directory listings (never had a real website)
FAKE_TIER_C = [
    'yelp.com',
    'yellowpages.com',
    'thumbtack.com',
    'angi.com', 'angieslist.com',
    'homeadvisor.com',
    'houzz.com',
    'bark.com',
    'networx.com',
    'manta.com',
    'chamberofcommerce.com',
    'linkedin.com',
    'twitter.com',
    'nextdoor.com',
    'tripadvisor.com',
    'bbb.org',
]

ALL_FAKE = FAKE_TIER_A + FAKE_TIER_B + FAKE_TIER_C

def classify_url(url: str) -> tuple[str, str]:
    """Returns (type, tier): type = 'none'|'fake'|'real', tier = 'A'|'B'|'C'|''"""
    if not url or not url.strip():
        return 'none', ''
    url_lower = url.lower()
    for p in FAKE_TIER_A:
        if p in url_lower:
            return 'fake', 'A'
    for p in FAKE_TIER_B:
        if p in url_lower:
            return 'fake', 'B'
    for p in FAKE_TIER_C:
        if p in url_lower:
            return 'fake', 'C'
    return 'real', ''

def check_ssl_url(url: str) -> bool:
    return url.lower().startswith('https://')

# ── Stage 2: HTTP triage ──────────────────────────────────

HEAD_WORKERS = 200
GET_WORKERS  = 150
HEAD_TIMEOUT = 5
GET_TIMEOUT  = 8

async def head_request(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    lead: dict,
    progress: dict,
) -> dict:
    url = lead.get('website', '').strip()
    lead.update({
        'http_status':  None,
        'redirect_url': None,
        'response_ms':  None,
        'alive':        False,
        'needs_get':    False,
        'method_used':  'head',
    })
    if not url:
        progress['done'] += 1
        return lead

    async with semaphore:
        start = time.time()
        try:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=HEAD_TIMEOUT),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                elapsed    = round((time.time() - start) * 1000)
                final_url  = str(resp.url)
                lead['http_status']  = resp.status
                lead['redirect_url'] = final_url if final_url != url else None
                lead['response_ms']  = elapsed
                lead['alive']        = resp.status < 400
                if resp.status in (403, 405, 501):
                    lead['needs_get'] = True
        except asyncio.TimeoutError:
            lead['http_status'] = 'timeout'
            lead['needs_get']   = True
        except aiohttp.ClientSSLError:
            lead['http_status'] = 'ssl_error'
            lead['alive']       = True
        except aiohttp.ClientConnectorError:
            lead['http_status'] = 'connection_error'
        except Exception:
            lead['http_status'] = 'error'
            lead['needs_get']   = True

    progress['done'] += 1
    _print_progress(progress)
    return lead

async def get_request(
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
                elapsed   = round((time.time() - start) * 1000)
                final_url = str(resp.url)
                lead['http_status']  = resp.status
                lead['redirect_url'] = final_url if final_url != url else None
                lead['response_ms']  = elapsed
                lead['alive']        = resp.status < 400
                lead['method_used']  = 'get'
                lead['needs_get']    = False
        except asyncio.TimeoutError:
            lead['http_status'] = 'timeout'
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
    _print_progress(progress)
    return lead

def _print_progress(progress: dict):
    done  = progress['done']
    total = progress['total']
    pct   = round(done / total * 100)
    filled = round(pct / 100 * 40)
    b = f"{G}{'█'*filled}{DIM}{'░'*(40-filled)}{RST}"
    print(f"  {b} {bold(str(pct)+'%')} {dim(str(done)+'/'+str(total))}", end='\r')

async def run_http_triage(leads: list) -> list:
    # HEAD pass
    sem  = asyncio.Semaphore(HEAD_WORKERS)
    prog = {'done': 0, 'total': len(leads)}
    conn = aiohttp.TCPConnector(limit=250, ssl=False)
    async with aiohttp.ClientSession(
        connector=conn,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        tasks   = [head_request(session, sem, l, prog) for l in leads]
        results = await asyncio.gather(*tasks)
    print()

    needs_get = [l for l in results if l.get('needs_get')]
    confirmed = [l for l in results if not l.get('needs_get')]

    alive_head = len([l for l in confirmed if l.get('alive')])
    dead_head  = len([l for l in confirmed if not l.get('alive')])
    print(f"    HEAD: {green(str(alive_head))} alive  {red(str(dead_head))} dead  "
          f"{yellow(str(len(needs_get)))} need GET fallback")

    # GET fallback
    if needs_get:
        sem2  = asyncio.Semaphore(GET_WORKERS)
        prog2 = {'done': 0, 'total': len(needs_get)}
        conn2 = aiohttp.TCPConnector(limit=200, ssl=False)
        async with aiohttp.ClientSession(
            connector=conn2,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        ) as session2:
            tasks2  = [get_request(session2, sem2, l, prog2) for l in needs_get]
            results2 = await asyncio.gather(*tasks2)
        print()
        alive_get = len([l for l in results2 if l.get('alive')])
        dead_get  = len([l for l in results2 if not l.get('alive')])
        print(f"    GET: {green(str(alive_get))} recovered alive  "
              f"{red(str(dead_get))} confirmed dead")
        return confirmed + results2

    return confirmed

# ── Stage 3: HTML technical analysis ─────────────────────

HTML_WORKERS = 40
HTML_TIMEOUT = 6

def extract_tech_score(html: str, url: str, response_ms: int) -> tuple[int, list]:
    issues = []
    score  = 10

    # SSL
    if not check_ssl_url(url):
        score -= 2
        issues.append("No SSL — browsers show 'Not Secure'")

    # Copyright year
    matches = re.findall(r'©\s*(\d{4})|copyright\s*(\d{4})', html, re.IGNORECASE)
    years   = [int(y) for pair in matches for y in pair if y]
    if years:
        oldest = min(years)
        age    = 2026 - oldest
        if age >= 8:
            score -= 2
            issues.append(f"Copyright {oldest} — site is {age} years old")
        elif age >= 5:
            score -= 1
            issues.append(f"Copyright {oldest} — possibly outdated")

    # Meta tags
    has_title    = bool(re.search(r'<title>[^<]{5,}</title>', html, re.IGNORECASE))
    has_desc     = bool(re.search(r'<meta[^>]+name=["\']description["\']', html, re.IGNORECASE))
    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE))
    if not has_title or not has_desc:
        score -= 1
        issues.append("Missing SEO meta tags")
    if not has_viewport:
        score -= 1
        issues.append("No viewport meta — likely not mobile friendly")

    # Contact info
    has_phone = bool(re.search(r'(\+1|1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', html))
    has_email = bool(re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}', html))
    has_form  = bool(re.search(r'<form[\s>]', html, re.IGNORECASE))
    if not has_phone and not has_email and not has_form:
        score -= 2
        issues.append("No contact info found")
    elif not has_phone and not has_form:
        score -= 1
        issues.append("No phone number or contact form")

    # Load time
    if response_ms and response_ms > 5000:
        score -= 1
        issues.append(f"Very slow load time ({round(response_ms/1000,1)}s)")
    elif response_ms and response_ms > 3000:
        score -= 1
        issues.append(f"Slow load time ({round(response_ms/1000,1)}s)")

    return max(score, 0), issues

async def analyse_html_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    lead: dict,
    progress: dict,
) -> dict:
    url = (lead.get('redirect_url') or lead.get('website', '')).strip()

    async with semaphore:
        try:
            async with asyncio.timeout(8):
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=HTML_TIMEOUT),
                    allow_redirects=True,
                    ssl=False,
                ) as resp:
                    html = await resp.text(errors='ignore')
                    ms   = lead.get('response_ms') or 0
                    score, issues = extract_tech_score(html, url, ms)
                    lead['tech_score']  = score
                    lead['tech_issues'] = ' | '.join(issues)
                    lead['has_ssl']     = check_ssl_url(url)
        except Exception:
            lead['tech_score']  = 3
            lead['tech_issues'] = 'Could not retrieve HTML — site likely slow or blocking'
            lead['has_ssl']     = check_ssl_url(url)

    progress['done'] += 1
    _print_progress(progress)
    return lead
async def run_html_analysis(leads: list) -> list:
    sem  = asyncio.Semaphore(HTML_WORKERS)
    prog = {'done': 0, 'total': len(leads)}
    conn = aiohttp.TCPConnector(limit=50, ssl=False)
    async with aiohttp.ClientSession(
        connector=conn,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        tasks   = [analyse_html_one(session, sem, l, prog) for l in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    print()

    cleaned = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            leads[i]['tech_score']  = 3
            leads[i]['tech_issues'] = 'Task failed — auto scored'
            leads[i]['has_ssl']     = check_ssl_url(leads[i].get('website', ''))
            cleaned.append(leads[i])
        else:
            cleaned.append(r)
    return cleaned
# ── Priority scoring ──────────────────────────────────────

def priority_score(lead: dict) -> int:
    score    = 0
    stage    = lead.get('pipeline_stage', '')
    reviews  = int(lead.get('review_count') or 0)
    fake_tier = lead.get('fake_tier', '')
    tech     = lead.get('tech_score', 10)
    ms       = lead.get('response_ms') or 0
    http_s   = lead.get('http_status')

    # Base from stage/tier
    if stage == 'no_website':
        score += 100
    elif stage == 'fake_A':
        score += 90
    elif stage == 'fake_B':
        score += 85
    elif stage == 'fake_C':
        score += 75
    elif stage == 'dead':
        score += 88
    elif stage == 'ssl_error':
        score += 70
    elif stage == 'timeout':
        score += 65
    elif stage == 'weak_site':
        score += max(0, (5 - tech) * 8)   # score 5→0pts, score 0→40pts

    # Review bonus
    if reviews >= 500:   score += 25
    elif reviews >= 200: score += 20
    elif reviews >= 100: score += 15
    elif reviews >= 50:  score += 10
    elif reviews >= 20:  score += 6
    elif reviews >= 10:  score += 3

    return min(score, 100)

def stage_label(stage: str) -> str:
    labels = {
        'no_website': red('NO WEBSITE'),
        'fake_A':     yellow('FAKE  [A]  '),
        'fake_B':     yellow('FAKE  [B]  '),
        'fake_C':     dim(   'FAKE  [C]  '),
        'dead':       red(   'DEAD SITE  '),
        'ssl_error':  yellow('SSL ERROR  '),
        'timeout':    magenta('TIMEOUT   '),
        'weak_site':  blue(  'WEAK SITE  '),
    }
    return labels.get(stage, dim('UNKNOWN    '))

def priority_bar(score: int) -> str:
    if score >= 90: return f"{R}{'█'*5} P{score:>3}{RST}"
    if score >= 75: return f"{Y}{'█'*4} P{score:>3}{RST}"
    if score >= 60: return f"{M}{'█'*3} P{score:>3}{RST}"
    if score >= 40: return f"{B}{'█'*2} P{score:>3}{RST}"
    return f"{DIM}{'█'*1} P{score:>3}{RST}"

# ── Main pipeline ─────────────────────────────────────────

def main():
    # Find input CSV
    if len(sys.argv) >= 2:
        csv_path = sys.argv[1]
    else:
        files = sorted(glob.glob("florida_targeted_*.csv"), reverse=True)
        if not files:
            files = sorted(glob.glob("florida_raw_*.csv"), reverse=True)
        if not files:
            print(red("No florida_targeted_*.csv found."))
            sys.exit(1)
        csv_path = files[0]

    print()
    print("═" * 70)
    print(f"  {bold(cyan('LeadGen — Full Lead Pipeline'))}")
    print(f"  {dim('Stage 1: Instant → Stage 2: HTTP → Stage 3: HTML → Ranked leads')}")
    print("═" * 70)
    print(f"  {dim('File: ' + csv_path)}")
    print(f"  {dim('Run:  ' + datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print()

    with open(csv_path, newline='', encoding='utf-8') as f:
        all_leads = list(csv.DictReader(f))

    # Initialise fields
    for l in all_leads:
        l['pipeline_stage'] = ''
        l['fake_tier']      = ''
        l['http_status']    = None
        l['redirect_url']   = None
        l['response_ms']    = None
        l['alive']          = False
        l['needs_get']      = False
        l['method_used']    = ''
        l['has_ssl']        = False
        l['tech_score']     = None
        l['tech_issues']    = ''
        l['priority_score'] = 0

    total = len(all_leads)
    print(f"  {bold(white(f'{total:,}'))} businesses loaded")
    print()

    # ══════════════════════════════════════════════════════
    # STAGE 1 — Instant good leads
    # ══════════════════════════════════════════════════════
    section("STAGE 1 — Instant Good Leads")
    print(f"  {dim('No website + Fake website classification')}")
    print()

    good_leads  = []
    to_triage   = []

    for lead in all_leads:
        has_website = lead.get('has_website', 'No')
        url         = lead.get('website', '').strip()

        if has_website == 'No' or not url:
            lead['pipeline_stage'] = 'no_website'
            good_leads.append(lead)
            continue

        url_type, tier = classify_url(url)

        if url_type == 'fake':
            lead['pipeline_stage'] = f'fake_{tier}'
            lead['fake_tier']      = tier
            good_leads.append(lead)
        else:
            to_triage.append(lead)

    no_web   = [l for l in good_leads if l['pipeline_stage'] == 'no_website']
    fake_a   = [l for l in good_leads if l['pipeline_stage'] == 'fake_A']
    fake_b   = [l for l in good_leads if l['pipeline_stage'] == 'fake_B']
    fake_c   = [l for l in good_leads if l['pipeline_stage'] == 'fake_C']

    print(f"  {red(bold(str(len(no_web))))}  no website at all")
    print(f"  {yellow(bold(str(len(fake_a))))}  fake Tier A  {dim('(Google discontinued / social profiles)')}")
    print(f"  {yellow(bold(str(len(fake_b))))}  fake Tier B  {dim('(free subdomain builders)')}")
    print(f"  {dim(bold(str(len(fake_c))))}  fake Tier C  {dim('(directory listings)')}")
    print(f"  {bold(str(len(to_triage)))}  real URLs → moving to Stage 2")
    print()

    # ══════════════════════════════════════════════════════
    # STAGE 2 — HTTP triage
    # ══════════════════════════════════════════════════════
    section("STAGE 2 — HTTP Triage")
    print(f"  {dim(f'HEAD + GET fallback on {len(to_triage):,} real URLs')}")
    print(f"  {dim(f'HEAD workers: {HEAD_WORKERS}  GET workers: {GET_WORKERS}')}")
    print()

    t2 = time.time()
    triaged = asyncio.run(run_http_triage(to_triage))
    e2 = round(time.time() - t2, 1)
    print(f"  {green('✓')} HTTP triage complete in {bold(str(e2)+'s')}")
    print()

    # Classify results
    to_html = []
    for lead in triaged:
        status = lead.get('http_status')
        alive  = lead.get('alive', False)

        # Dead → good leads immediately
        if not alive and status not in ('ssl_error',):
            if status in ('connection_error', 'dead') or \
               (isinstance(status, int) and status in (404, 500, 502, 503, 410)):
                lead['pipeline_stage'] = 'dead'
                good_leads.append(lead)
                continue

        # SSL error → Stage 3 for HTML check
        if status == 'ssl_error':
            lead['pipeline_stage'] = 'ssl_error'
            to_html.append(lead)
            continue

        # 403 → skip entirely
        if status == 403 or (isinstance(status, int) and status == 403):
            continue

        # Timeout after both HEAD + GET → auto score 3, add to good leads
        if status == 'timeout' and not alive:
            lead['pipeline_stage'] = 'timeout'
            lead['tech_score']     = 3
            lead['tech_issues']    = 'Site did not respond — likely dead or blocking'
            lead['has_ssl']        = check_ssl_url(lead.get('website', ''))
            good_leads.append(lead)
            continue

        # 200 OK and redirects → Stage 3
        if alive:
            to_html.append(lead)
            continue

    dead_s2    = [l for l in good_leads if l['pipeline_stage'] == 'dead']
    timeout_s2 = [l for l in good_leads if l['pipeline_stage'] == 'timeout']

    print(f"  {red(bold(str(len(dead_s2))))}  dead sites added to good leads")
    print(f"  {magenta(bold(str(len(timeout_s2))))}  timeouts auto-scored (3/10) added to good leads")
    print(f"  {bold(str(len(to_html)))}  alive sites → moving to Stage 3")
    print()

    # ══════════════════════════════════════════════════════
    # STAGE 3 — HTML technical analysis
    # ══════════════════════════════════════════════════════
    section("STAGE 3 — HTML Technical Analysis")
    print(f"  {dim(f'Analysing {len(to_html):,} alive sites  ({HTML_WORKERS} workers)')}")
    print()

    t3 = time.time()
    analysed = asyncio.run(run_html_analysis(to_html))
    e3 = round(time.time() - t3, 1)
    print(f"  {green('✓')} HTML analysis complete in {bold(str(e3)+'s')}")
    print()

    # Score distribution
    score_buckets = defaultdict(int)
    for l in analysed:
        s = l.get('tech_score', 10)
        if s <= 2:   score_buckets['0-2'] += 1
        elif s <= 4: score_buckets['3-4'] += 1
        elif s <= 5: score_buckets['5']   += 1
        elif s <= 7: score_buckets['6-7'] += 1
        else:        score_buckets['8-10']+= 1

    print(f"  {bold('Technical score distribution:')}")
    max_b = max(score_buckets.values()) if score_buckets else 1
    for bucket, count in [('0-2','0-2'),('3-4','3-4'),('5','5'),('6-7','6-7'),('8-10','8-10')]:
        cnt = score_buckets.get(count, 0)
        col = R if bucket in ('0-2','3-4') else Y if bucket == '5' else G
        b   = bar(cnt, max_b, width=20, color=col)
        add = red(' ← added to good leads') if bucket in ('0-2','3-4','5') else ''
        print(f"    {col}Score {bucket.ljust(5)}{RST} {b} {bold(str(cnt))}{add}")
    print()

    # Add weak sites (score ≤ 5) to good leads
    for lead in analysed:
        score = lead.get('tech_score', 10)
        if score <= 5:
            lead['pipeline_stage'] = 'weak_site'
            good_leads.append(lead)
        # else: deprioritised — has a decent website, skip

    weak_added = [l for l in good_leads if l['pipeline_stage'] == 'weak_site']
    skipped    = len(analysed) - len(weak_added)

    print(f"  {blue(bold(str(len(weak_added))))}  weak sites (score ≤ 5) added to good leads")
    print(f"  {dim(bold(str(skipped)))}  sites with decent websites — skipped")
    print()

    # ══════════════════════════════════════════════════════
    # FINAL SCORING & RANKING
    # ══════════════════════════════════════════════════════
    section("FINAL SCORING & RANKING")

    for lead in good_leads:
        lead['priority_score'] = priority_score(lead)

    good_leads.sort(key=lambda x: x['priority_score'], reverse=True)

    total_gl  = len(good_leads)
    hv_leads  = [l for l in good_leads if int(l.get('review_count') or 0) >= 20]

    print(f"\n  {bold(white(str(total_gl)))} total good leads")
    print(f"  {bold(yellow(str(len(hv_leads))))} high-value (20+ reviews)")
    print()

    # Stage breakdown
    stage_counts = defaultdict(int)
    for l in good_leads:
        stage_counts[l['pipeline_stage']] += 1

    stage_order = ['no_website','fake_A','fake_B','fake_C','dead','ssl_error','timeout','weak_site']
    max_sc = max(stage_counts.values()) if stage_counts else 1
    print(f"  {bold('By stage:')}")
    for stage in stage_order:
        cnt = stage_counts.get(stage, 0)
        if cnt == 0: continue
        b   = bar(cnt, max_sc, width=20)
        print(f"    {stage_label(stage)} {b} {bold(str(cnt))}")
    print()

    # Top 30 preview
    print(f"  {bold('TOP 30 LEADS:')}")
    divider()
    print(f"  {dim('Priority    Stage         Business                      City          Reviews')}")
    divider()
    for lead in good_leads[:30]:
        name    = lead.get('name', '')[:28].ljust(28)
        city    = lead.get('city', '')[:13].ljust(13)
        reviews = int(lead.get('review_count') or 0)
        rev_str = f"{reviews:>4}★" if reviews else dim("  no★")
        print(f"  {priority_bar(lead['priority_score'])}  "
              f"{stage_label(lead['pipeline_stage'])}  "
              f"{white(name)}  {dim(city)}  {yellow(str(rev_str))}")
    print()

    # Industry breakdown of good leads
    print(f"  {bold('Good Leads by Industry:')}")
    by_ind = defaultdict(list)
    for l in good_leads:
        by_ind[l.get('industry','')].append(l)
    ind_rows = sorted(by_ind.items(), key=lambda x: -len(x[1]))
    max_i = max(len(v) for _, v in ind_rows) if ind_rows else 1
    print(f"  {'Industry':<28} {'Total':>6} {'HV':>5}  Bar")
    divider()
    for ind, items in ind_rows:
        hv_ = sum(1 for l in items if int(l.get('review_count') or 0) >= 20)
        b   = bar(len(items), max_i, width=20)
        print(f"  {white(ind[:28].ljust(28))} {len(items):>6} {yellow(str(hv_).rjust(5))}  {b}")
    print()

    # City breakdown
    print(f"  {bold('Good Leads by City:')}")
    by_city = defaultdict(list)
    for l in good_leads:
        by_city[l.get('city','')].append(l)
    city_rows = sorted(by_city.items(), key=lambda x: -len(x[1]))
    max_c = max(len(v) for _, v in city_rows) if city_rows else 1
    print(f"  {'City':<22} {'Total':>6} {'HV':>5}  Bar")
    divider()
    for city, items in city_rows:
        hv_ = sum(1 for l in items if int(l.get('review_count') or 0) >= 20)
        b   = bar(len(items), max_c, width=22)
        print(f"  {white(city.ljust(22))} {len(items):>6} {yellow(str(hv_).rjust(5))}  {b}")
    print()

    # ══════════════════════════════════════════════════════
    # SAVE OUTPUT
    # ══════════════════════════════════════════════════════
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_path = f"pipeline_leads_{ts}.csv"
    hv_path  = f"pipeline_leads_highvalue_{ts}.csv"

    base_fields = [
        'city','area','industry','name','phone','website','has_website',
        'rating','review_count','address','place_id',
    ]
    extra_fields = [
        'pipeline_stage','fake_tier','http_status','redirect_url',
        'response_ms','has_ssl','tech_score','tech_issues','priority_score',
    ]
    all_fields = base_fields + extra_fields

    def write_csv(path, rows):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=all_fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

    write_csv(all_path, good_leads)
    write_csv(hv_path, hv_leads)

    print("═" * 70)
    print(f"  {bold(cyan('PIPELINE COMPLETE'))}")
    print("═" * 70)
    print(f"  {green('✓')} All good leads    : {bold(all_path)} {dim('('+str(total_gl)+' leads)')}")
    print(f"  {green('✓')} High-value only   : {bold(hv_path)} {dim('('+str(len(hv_leads))+' leads)')}")
    print()

if __name__ == '__main__':
    main()