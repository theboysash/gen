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

FAKE_TIER_A = [
    'business.site',
    'facebook.com', 'fb.com', 'fb.me',
    'instagram.com',
    'linktr.ee', 'linktree.com',
    'beacons.ai',
    'bio.site',
    'tiktok.com',
    'youtube.com',
]

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

def classify_url(url: str) -> tuple:
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

# ── HTTP triage config ────────────────────────────────────

HEAD_WORKERS = 200
GET_WORKERS  = 150
HEAD_TIMEOUT = 5
GET_TIMEOUT  = 8

def _print_progress(progress: dict):
    done   = progress['done']
    total  = progress['total']
    pct    = round(done / total * 100)
    filled = round(pct / 100 * 40)
    b = f"{G}{'█'*filled}{DIM}{'░'*(40-filled)}{RST}"
    print(f"  {b} {bold(str(pct)+'%')} {dim(str(done)+'/'+str(total))}", end='\r')

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
                elapsed   = round((time.time() - start) * 1000)
                final_url = str(resp.url)
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


async def run_http_triage(leads: list) -> list:
    # HEAD pass
    sem  = asyncio.Semaphore(HEAD_WORKERS)
    prog = {'done': 0, 'total': len(leads)}
    conn = aiohttp.TCPConnector(limit=250, ssl=False)
    async with aiohttp.ClientSession(
        connector=conn,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:
        tasks   = [head_request(session, sem, lead, prog) for lead in leads]
        results = await asyncio.gather(*tasks)
    print()

    needs_get = [l for l in results if l.get('needs_get')]
    confirmed = [l for l in results if not l.get('needs_get')]
    alive_h   = len([l for l in confirmed if l.get('alive')])
    dead_h    = len([l for l in confirmed if not l.get('alive')])
    print(f"    HEAD: {green(str(alive_h))} alive  "
          f"{red(str(dead_h))} dead  "
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
            tasks2   = [get_request(session2, sem2, l, prog2) for l in needs_get]
            results2 = await asyncio.gather(*tasks2)
        print()
        alive_g = len([l for l in results2 if l.get('alive')])
        dead_g  = len([l for l in results2 if not l.get('alive')])
        print(f"    GET: {green(str(alive_g))} recovered  "
              f"{red(str(dead_g))} confirmed dead")
        return confirmed + results2

    return confirmed


# ── Priority scoring ──────────────────────────────────────

def priority_score(lead: dict) -> int:
    score   = 0
    stage   = lead.get('pipeline_stage', '')
    reviews = int(lead.get('review_count') or 0)

    if stage == 'no_website':   score += 100
    elif stage == 'fake_A':     score += 90
    elif stage == 'dead':       score += 88
    elif stage == 'fake_B':     score += 85
    elif stage == 'ssl_error':  score += 70
    elif stage == 'fake_C':     score += 75
    elif stage == 'timeout':    score += 65
    elif stage == 'alive':      score += 20  # pending stage 3

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
        'fake_A':     yellow('FAKE  [A] '),
        'fake_B':     yellow('FAKE  [B] '),
        'fake_C':     dim(   'FAKE  [C] '),
        'dead':       red(   'DEAD      '),
        'ssl_error':  yellow('SSL ERROR '),
        'timeout':    magenta('TIMEOUT  '),
        'alive':      blue(  'ALIVE*    '),
    }
    return labels.get(stage, dim('UNKNOWN   '))

def priority_bar(score: int) -> str:
    if score >= 90: return f"{R}{'█'*5} P{score:>3}{RST}"
    if score >= 75: return f"{Y}{'█'*4} P{score:>3}{RST}"
    if score >= 60: return f"{M}{'█'*3} P{score:>3}{RST}"
    if score >= 40: return f"{B}{'█'*2} P{score:>3}{RST}"
    return f"{DIM}{'█'*1} P{score:>3}{RST}"


# ── Main ──────────────────────────────────────────────────

def main():
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
    print(f"  {bold(cyan('LeadGen — Pipeline Stage 1 + 2'))}")
    print(f"  {dim('Instant good leads + HTTP triage')}")
    print("═" * 70)
    print(f"  {dim('File: ' + csv_path)}")
    print(f"  {dim('Run:  ' + datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print()

    with open(csv_path, newline='', encoding='utf-8') as f:
        all_leads = list(csv.DictReader(f))

    for l in all_leads:
        l['pipeline_stage'] = ''
        l['fake_tier']      = ''
        l['http_status']    = None
        l['redirect_url']   = None
        l['response_ms']    = None
        l['alive']          = False
        l['needs_get']      = False
        l['method_used']    = ''
        l['has_ssl']        = check_ssl_url(l.get('website', ''))

    total = len(all_leads)
    print(f"  {bold(white(f'{total:,}'))} businesses loaded")
    print()

    # ══════════════════════════════════════════════════════
    # STAGE 1 — Instant good leads
    # ══════════════════════════════════════════════════════
    section("STAGE 1 — Instant Good Leads")
    print(f"  {dim('No website + Fake website classification')}")
    print()

    good_leads = []
    to_triage  = []

    for lead in all_leads:
        url = lead.get('website', '').strip()

        if lead.get('has_website', 'No') == 'No' or not url:
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

    no_web  = [l for l in good_leads if l['pipeline_stage'] == 'no_website']
    fake_a  = [l for l in good_leads if l['pipeline_stage'] == 'fake_A']
    fake_b  = [l for l in good_leads if l['pipeline_stage'] == 'fake_B']
    fake_c  = [l for l in good_leads if l['pipeline_stage'] == 'fake_C']

    print(f"  {red(bold(str(len(no_web))))}  no website at all")
    print(f"  {yellow(bold(str(len(fake_a))))}  fake Tier A  {dim('(Google discontinued / social profiles)')}")
    print(f"  {yellow(bold(str(len(fake_b))))}  fake Tier B  {dim('(free subdomain builders)')}")
    print(f"  {dim(bold(str(len(fake_c))))}  fake Tier C  {dim('(directory listings)')}")
    print(f"  {bold(str(len(to_triage)))}  real URLs → Stage 2")
    print()

    # ══════════════════════════════════════════════════════
    # STAGE 2 — HTTP triage
    # ══════════════════════════════════════════════════════
    section("STAGE 2 — HTTP Triage")
    print(f"  {dim(f'HEAD + GET fallback on {len(to_triage):,} real URLs')}")
    print(f"  {dim(f'HEAD workers: {HEAD_WORKERS}  GET workers: {GET_WORKERS}')}")
    print()

    t2      = time.time()
    triaged = asyncio.run(run_http_triage(to_triage))
    e2      = round(time.time() - t2, 1)
    print(f"  {green('✓')} HTTP triage complete in {bold(str(e2)+'s')}")
    print()

    # Classify and split
    alive_for_stage3 = []

    for lead in triaged:
        status = lead.get('http_status')
        alive  = lead.get('alive', False)

        # 403 → skip entirely
        if status == 403 or status == '403':
            continue

        # Dead signals → good leads now
        if not alive and status not in ('ssl_error',):
            if status in ('connection_error', 'dead') or \
               (isinstance(status, int) and status in (404, 500, 502, 503, 410)):
                lead['pipeline_stage'] = 'dead'
                good_leads.append(lead)
                continue

        # SSL error → good leads now
        if status == 'ssl_error':
            lead['pipeline_stage'] = 'ssl_error'
            good_leads.append(lead)
            continue

        # Timeout after both → good leads with auto note
        if status == 'timeout' and not alive:
            lead['pipeline_stage'] = 'timeout'
            good_leads.append(lead)
            continue

        # Alive (200/redirect) → save for stage 3
        if alive:
            lead['pipeline_stage'] = 'alive'
            alive_for_stage3.append(lead)
            continue

    # Status breakdown
    status_counts = defaultdict(int)
    for l in triaged:
        status_counts[str(l.get('http_status', 'unknown'))] += 1

    print(f"  {bold('HTTP Status Breakdown:')}")
    max_sc = max(status_counts.values()) if status_counts else 1
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1])[:10]:
        col = green if status == '200' else red if status in ('dead','connection_error') or (status.isdigit() and int(status) >= 400) else yellow
        b   = bar(count, max_sc, width=18, color=G)
        print(f"    {col(str(status).ljust(20))} {b} {bold(str(count))}")
    print()

    dead_s2    = [l for l in good_leads if l['pipeline_stage'] == 'dead']
    ssl_s2     = [l for l in good_leads if l['pipeline_stage'] == 'ssl_error']
    timeout_s2 = [l for l in good_leads if l['pipeline_stage'] == 'timeout']

    print(f"  {red(bold(str(len(dead_s2))))}   dead sites → good leads")
    print(f"  {yellow(bold(str(len(ssl_s2))))}   SSL errors → good leads")
    print(f"  {magenta(bold(str(len(timeout_s2))))}   timeouts   → good leads")
    print(f"  {blue(bold(str(len(alive_for_stage3))))}  alive sites → saved for Stage 3")
    print()

    # ══════════════════════════════════════════════════════
    # SCORE + RANK current good leads
    # ══════════════════════════════════════════════════════
    for lead in good_leads:
        lead['priority_score'] = priority_score(lead)
    good_leads.sort(key=lambda x: x['priority_score'], reverse=True)

    total_gl = len(good_leads)
    hv_leads = [l for l in good_leads if int(l.get('review_count') or 0) >= 20]

    print("═" * 70)
    print(f"  {bold(cyan('CURRENT GOOD LEADS  (Stages 1 + 2)'))}")
    print("═" * 70)
    print(f"  {bold(white(str(total_gl)))} confirmed good leads")
    print(f"  {bold(yellow(str(len(hv_leads))))} high-value (20+ reviews)")
    print(f"  {bold(blue(str(len(alive_for_stage3))))} alive sites pending Stage 3")
    print()

    # Stage breakdown
    stage_counts = defaultdict(int)
    for l in good_leads:
        stage_counts[l['pipeline_stage']] += 1
    max_sc2 = max(stage_counts.values()) if stage_counts else 1
    print(f"  {bold('By stage:')}")
    for stage in ['no_website','fake_A','fake_B','fake_C','dead','ssl_error','timeout']:
        cnt = stage_counts.get(stage, 0)
        if cnt == 0: continue
        b = bar(cnt, max_sc2, width=22)
        print(f"    {stage_label(stage)} {b} {bold(str(cnt))}")
    print()

    # By industry
    print(f"  {bold('By Industry:')}")
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

    # By city
    print(f"  {bold('By City:')}")
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

    # Top 30
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

    # ══════════════════════════════════════════════════════
    # SAVE
    # ══════════════════════════════════════════════════════
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_fields  = ['city','area','industry','name','phone','website',
                    'has_website','rating','review_count','address','place_id']
    extra_fields = ['pipeline_stage','fake_tier','http_status','redirect_url',
                    'response_ms','has_ssl','priority_score']
    all_fields   = base_fields + extra_fields

    def write_csv(path, rows):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=all_fields, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

    good_path  = f"pipeline_s1s2_good_{ts}.csv"
    alive_path = f"pipeline_s1s2_alive_{ts}.csv"
    hv_path    = f"pipeline_s1s2_highvalue_{ts}.csv"

    write_csv(good_path,  good_leads)
    write_csv(alive_path, alive_for_stage3)
    write_csv(hv_path,    hv_leads)

    print("═" * 70)
    print(f"  {bold(cyan('SAVED'))}")
    print("═" * 70)
    print(f"  {green('✓')} Good leads (S1+S2)  : {bold(good_path)}  {dim('('+str(total_gl)+' leads)')}")
    print(f"  {green('✓')} Alive → Stage 3     : {bold(alive_path)}  {dim('('+str(len(alive_for_stage3))+' sites)')}")
    print(f"  {green('✓')} High-value only      : {bold(hv_path)}  {dim('('+str(len(hv_leads))+' leads)')}")
    print()

if __name__ == '__main__':
    main()