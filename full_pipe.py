#!/usr/bin/env python3
"""
LeadGen Florida — Full Pipeline
Runs: triage → analysis
Usage: python run_pipeline.py [raw_csv]
"""

import asyncio
import aiohttp
import csv
import sys
import glob
import time
from datetime import datetime
from collections import defaultdict

# ── ANSI colours ──────────────────────────────────────────
R  = "\033[91m"; G  = "\033[92m"; Y  = "\033[93m"; B  = "\033[94m"
M  = "\033[95m"; C  = "\033[96m"; W  = "\033[97m"; DIM= "\033[2m"
BLD= "\033[1m";  RST= "\033[0m"

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
def pct(part, total):
    return f"{round(part/total*100)}%" if total else "0%"
def avg(items, key):
    vals = [float(x.get(key) or 0) for x in items if x.get(key) and str(x.get(key)).strip()]
    return round(sum(vals)/len(vals), 1) if vals else 0

# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
HEAD_WORKERS = 250
GET_WORKERS  = 200
HEAD_TIMEOUT = 5
GET_TIMEOUT  = 8

FAKE_PATTERNS = [
    'facebook.com','fb.com','fb.me','twitter.com','instagram.com',
    'wixsite.com','wix.com','weebly.com','my.canva.site','canva.site',
    'business.site','squarespace.com','linktr.ee','linktree.com',
    'yellowpages.com','yelp.com','tripadvisor.com','thumbtack.com',
    'angieslist.com','angi.com','homeadvisor.com','houzz.com',
    'linkedin.com','nextdoor.com','google.com/maps','maps.google.com',
    'cylex','hotfrog','manta.com','bizapedia.com','chamberofcommerce.com',
    'bark.com','networx.com','mysite.com','godaddysites.com',
    'wordpress.com','blogspot.com','sites.google.com',
]

# ══════════════════════════════════════════════════════════
# TRIAGE — helpers
# ══════════════════════════════════════════════════════════

def classify_url(url):
    if not url or url.strip() == '':
        return 'none'
    url_lower = url.lower()
    for p in FAKE_PATTERNS:
        if p in url_lower:
            return 'fake'
    return 'real'

def check_ssl(url):
    return url.lower().startswith('https://')

async def head_one(session, semaphore, lead, progress):
    url = lead.get('website', '').strip()
    result = {**lead, 'http_status': None, 'redirect_url': None,
              'response_ms': None, 'alive': False, 'needs_get': False, 'method_used': 'head'}
    if not url:
        progress['done'] += 1
        return result
    async with semaphore:
        start = time.time()
        try:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=HEAD_TIMEOUT),
                                    allow_redirects=True, ssl=False) as resp:
                elapsed = round((time.time()-start)*1000)
                final = str(resp.url)
                result.update({'http_status': resp.status,
                                'redirect_url': final if final != url else None,
                                'response_ms': elapsed, 'alive': resp.status < 400})
                if resp.status in (405, 501, 403):
                    result['needs_get'] = True
        except asyncio.TimeoutError:
            result.update({'http_status': 'timeout', 'needs_get': True})
        except aiohttp.ClientSSLError:
            result.update({'http_status': 'ssl_error', 'alive': True})
        except aiohttp.ClientConnectorError:
            result['http_status'] = 'connection_error'
        except Exception:
            result.update({'http_status': 'error', 'needs_get': True})
    progress['done'] += 1
    if progress['done'] % 500 == 0 or progress['done'] == progress['total']:
        p = round(progress['done']/progress['total']*100)
        f = round(p/100*40)
        print(f"  {G}{'█'*f}{DIM}{'░'*(40-f)}{RST} {bold(str(p)+'%')} {dim(str(progress['done'])+'/'+str(progress['total']))}", end='\r')
    return result

async def get_one(session, semaphore, lead, progress):
    url = lead.get('website', '').strip()
    async with semaphore:
        start = time.time()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=GET_TIMEOUT),
                                   allow_redirects=True, ssl=False) as resp:
                elapsed = round((time.time()-start)*1000)
                final = str(resp.url)
                lead.update({'http_status': resp.status,
                             'redirect_url': final if final != url else None,
                             'response_ms': elapsed, 'alive': resp.status < 400,
                             'method_used': 'get', 'needs_get': False})
        except asyncio.TimeoutError:
            lead.update({'http_status': 'dead', 'alive': False, 'method_used': 'get'})
        except aiohttp.ClientSSLError:
            lead.update({'http_status': 'ssl_error', 'alive': True, 'method_used': 'get'})
        except Exception:
            lead.update({'http_status': 'dead', 'alive': False, 'method_used': 'get'})
    progress['done'] += 1
    if progress['done'] % 250 == 0 or progress['done'] == progress['total']:
        p = round(progress['done']/progress['total']*100)
        f = round(p/100*40)
        print(f"  {G}{'█'*f}{DIM}{'░'*(40-f)}{RST} {bold(str(p)+'%')} {dim(str(progress['done'])+'/'+str(progress['total']))}", end='\r')
    return lead

async def _run_head(leads):
    sem  = asyncio.Semaphore(HEAD_WORKERS)
    prog = {'done': 0, 'total': len(leads)}
    conn = aiohttp.TCPConnector(limit=300, ssl=False)
    async with aiohttp.ClientSession(connector=conn,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}) as session:
        results = await asyncio.gather(*[head_one(session, sem, l, prog) for l in leads])
    print()
    return list(results)

async def _run_get(leads):
    sem  = asyncio.Semaphore(GET_WORKERS)
    prog = {'done': 0, 'total': len(leads)}
    conn = aiohttp.TCPConnector(limit=300, ssl=False)
    async with aiohttp.ClientSession(connector=conn,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}) as session:
        results = await asyncio.gather(*[get_one(session, sem, l, prog) for l in leads])
    print()
    return list(results)

def score_lead(lead):
    score    = 0
    url_type = lead.get('url_type', 'none')
    status   = lead.get('http_status')
    reviews  = int(lead.get('review_count') or 0)

    if url_type == 'none':                                  score += 100
    elif isinstance(status, int) and status >= 400:         score += 90
    elif status in ('dead', 'connection_error'):            score += 90
    elif status == 'ssl_error':                             score += 85
    elif url_type == 'fake':                                score += 80
    elif status == 'timeout':                               score += 75
    else:                                                   score += 20

    if url_type == 'real' and not lead.get('has_ssl'):      score += 15

    if reviews >= 200:    score += 20
    elif reviews >= 100:  score += 15
    elif reviews >= 50:   score += 10
    elif reviews >= 20:   score += 7
    elif reviews >= 10:   score += 3

    ms = lead.get('response_ms')
    if isinstance(ms, int):
        if ms > 5000:   score += 8
        elif ms > 3000: score += 4

    return min(score, 100)

def status_display(lead):
    status   = lead.get('http_status')
    url_type = lead.get('url_type', 'real')
    if url_type == 'none':             return red("NO WEBSITE")
    if url_type == 'fake':             return yellow("FAKE SITE ")
    if status == 'ssl_error':          return yellow("SSL ERROR ")
    if status in ('dead','connection_error'): return red("DEAD      ")
    if status == 'timeout':            return magenta("TIMEOUT   ")
    if isinstance(status, int):
        if status == 200:              return green("200 OK    ")
        if status >= 400:              return red(f"{status} ERROR ")
        return dim(f"{status}       ")
    return dim(str(status)[:10].ljust(10))

def priority_display(score):
    if score >= 90: return f"{R}{'█'*5} P{score:>3}{RST}"
    if score >= 75: return f"{Y}{'█'*4} P{score:>3}{RST}"
    if score >= 50: return f"{M}{'█'*3} P{score:>3}{RST}"
    return f"{DIM}{'█'*2} P{score:>3}{RST}"

# ══════════════════════════════════════════════════════════
# TRIAGE — main
# ══════════════════════════════════════════════════════════

def run_triage(csv_path):
    print()
    print('═'*70)
    print(f"  {bold(cyan('STAGE 1 — TRIAGE'))}  {dim('HEAD → GET → classify → score')}")
    print('═'*70)

    with open(csv_path, newline='', encoding='utf-8') as f:
        all_leads = list(csv.DictReader(f))

    no_url  = [l for l in all_leads if not l.get('website','').strip()]
    has_url = [l for l in all_leads if l.get('website','').strip()]
    print(f"  {bold(white(f'{len(all_leads):,}'))} loaded  |  {green(str(len(no_url)))} no URL  |  {yellow(str(len(has_url)))} have URL")
    print()

    # HEAD
    print(f"{bold('1a')} HEAD ({HEAD_WORKERS} workers)")
    print('─'*70)
    t0 = time.time()
    head_results = asyncio.run(_run_head(has_url))
    print(f"  {green('✓')} {bold(str(round(time.time()-t0,1))+'s')}")

    needs_get = [l for l in head_results if l.get('needs_get')]
    confirmed = [l for l in head_results if not l.get('needs_get')]
    print(f"  alive {green(str(len([l for l in confirmed if l.get('alive')])))}"
          f"  dead {red(str(len([l for l in confirmed if not l.get('alive')])))}"
          f"  GET fallback {yellow(str(len(needs_get)))}")
    print()

    # GET fallback
    print(f"{bold('1b')} GET fallback ({GET_WORKERS} workers, {len(needs_get)} sites)")
    print('─'*70)
    t0 = time.time()
    get_results = asyncio.run(_run_get(needs_get))
    print(f"  {green('✓')} {bold(str(round(time.time()-t0,1))+'s')}")
    print(f"  recovered {green(str(len([l for l in get_results if l.get('alive')])))}"
          f"  dead {red(str(len([l for l in get_results if not l.get('alive')])))}")
    print()

    # Classify
    all_checked = confirmed + get_results
    for l in all_checked:
        url   = l.get('website','')
        final = l.get('redirect_url') or url
        l['url_type']  = classify_url(final)
        l['has_ssl']   = check_ssl(final or url)
        l['final_url'] = final

    for l in no_url:
        l.update({'url_type':'none','has_ssl':False,'final_url':'',
                  'http_status':None,'alive':False,'response_ms':None,
                  'redirect_url':None,'needs_get':False,'method_used':'none'})

    all_combined = no_url + all_checked

    # Score & sort
    for l in all_combined:
        l['priority_score'] = score_lead(l)
    all_combined.sort(key=lambda x: x['priority_score'], reverse=True)

    # Status breakdown
    print(f"  {bold('HTTP Status Breakdown:')}")
    sc = defaultdict(int)
    for l in all_checked: sc[str(l.get('http_status','unknown'))] += 1
    max_sc = max(sc.values()) if sc else 1
    for status, count in sorted(sc.items(), key=lambda x: -x[1])[:12]:
        b   = bar(count, max_sc, width=20)
        col = green if status == '200' else red if status in ('dead','connection_error','ssl_error') or (status.isdigit() and int(status) >= 400) else cyan
        print(f"    {col(str(status).ljust(20))} {b} {bold(str(count))}")
    print()

    # URL type breakdown
    fake_c = sum(1 for l in all_combined if l.get('url_type')=='fake')
    real_c = sum(1 for l in all_combined if l.get('url_type')=='real')
    none_c = sum(1 for l in all_combined if l.get('url_type')=='none')
    print(f"  {red(bold(str(none_c)))} no website  {yellow(bold(str(fake_c)))} fake  {green(bold(str(real_c)))} real")
    print()

    # Priority distribution
    p100 = [l for l in all_combined if l['priority_score']==100]
    p90  = [l for l in all_combined if 90 <= l['priority_score'] < 100]
    p75  = [l for l in all_combined if 75 <= l['priority_score'] < 90]
    plo  = [l for l in all_combined if l['priority_score'] < 75]
    mx   = max(len(p100),len(p90),len(p75),len(plo),1)
    print(f"  {bold('Priority Distribution:')}")
    print(f"    {red('P100 no website'   .ljust(22))} {bar(len(p100),mx,25,color=R)} {bold(red(str(len(p100))))}")
    print(f"    {red('P90-99 dead/dying' .ljust(22))} {bar(len(p90), mx,25,color=R)} {bold(red(str(len(p90))))}")
    print(f"    {yellow('P75-89 fake/ssl'   .ljust(22))} {bar(len(p75), mx,25,color=Y)} {bold(yellow(str(len(p75))))}")
    print(f"    {dim('P0-74 lower'       .ljust(22))} {bar(len(plo), mx,25,color=DIM)} {bold(dim(str(len(plo))))}")
    print()

    # Top 30 preview
    print(f"{bold('TOP 30 LEADS')}")
    print('─'*70)
    print(f"  {dim('Priority   Status       Business                      City          Reviews')}")
    print(f"  {dim('─'*67)}")
    for l in all_combined[:30]:
        name    = l.get('name','Unknown')[:28].ljust(28)
        city    = l.get('city','')[:13].ljust(13)
        reviews = int(l.get('review_count') or 0)
        rev_str = f"{reviews:>4}★" if reviews else dim("  no★")
        print(f"  {priority_display(l['priority_score'])}  {status_display(l)}  {white(name)}  {dim(city)}  {yellow(str(rev_str))}")
    print()

    # Determine good leads (no website, fake, dead, ssl_error)
    good_leads = [l for l in all_combined
                  if l.get('url_type') in ('none','fake')
                  or l.get('http_status') in ('ssl_error','dead','connection_error','timeout')
                  or (isinstance(l.get('http_status'), int) and l['http_status'] >= 400)]

    # Assign lead_tier for analysis stage
    for l in good_leads:
        url_type = l.get('url_type','none')
        status   = l.get('http_status')
        if url_type == 'none':
            l['lead_tier'] = 'no_website'
        elif url_type == 'fake':
            l['lead_tier'] = 'fake_website'
        elif status == 'ssl_error':
            l['lead_tier'] = 'ssl_error'
        else:
            l['lead_tier'] = 'dead_site'

    # Save triaged CSV (all leads)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    triage_out = f"florida_triaged_{ts}.csv"
    fields = list(all_combined[0].keys()) if all_combined else []
    with open(triage_out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_combined)
    print(f"  {green('✓')} Triaged CSV saved: {bold(triage_out)}")

    # Save good leads CSV
    good_out = f"good_leads_{ts}.csv"
    if good_leads:
        fields_g = list(good_leads[0].keys())
        with open(good_out, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields_g)
            w.writeheader()
            w.writerows(good_leads)
    print(f"  {green('✓')} Good leads CSV saved: {bold(good_out)}  ({len(good_leads)} leads)")
    print()

    return good_out

# ══════════════════════════════════════════════════════════
# ANALYSIS helpers
# ══════════════════════════════════════════════════════════

BUCKET_ORDER = ['0 reviews','1-9 reviews','10-19 reviews','20-49 reviews',
                '50-99 reviews','100-199 reviews','200+ reviews']

def review_bucket(r):
    if r == 0:    return '0 reviews'
    if r <= 9:    return '1-9 reviews'
    if r <= 19:   return '10-19 reviews'
    if r <= 49:   return '20-49 reviews'
    if r <= 99:   return '50-99 reviews'
    if r <= 199:  return '100-199 reviews'
    return '200+ reviews'

def tier_color(t):
    return {'no_website':red,'fake_website':yellow,'dead_site':magenta,'ssl_error':yellow}.get(t,dim)

def tier_label(t):
    return {'no_website':'No Website','fake_website':'Fake Site',
            'dead_site':'Dead Site','ssl_error':'SSL Error'}.get(t,t)

def section(title):
    print()
    print('═'*70)
    print(f"  {bold(cyan(title))}")
    print('═'*70)

def subsection(title):
    print()
    print(f"  {bold(white('── '+title))}")
    print('─'*70)

# ══════════════════════════════════════════════════════════
# ANALYSIS — main
# ══════════════════════════════════════════════════════════

def run_analysis(path):
    with open(path, newline='', encoding='utf-8') as f:
        leads = list(csv.DictReader(f))

    for l in leads:
        l['_reviews'] = int(l.get('review_count') or 0)
        l['_rating']  = float(l.get('rating') or 0)
        l['_tier']    = l.get('lead_tier','unknown')
        l['_hv']      = l['_reviews'] >= 20

    total = len(leads)
    hv    = [l for l in leads if l['_hv']]

    print()
    print('═'*70)
    print(f"  {bold(cyan('LeadGen — Good Leads Analysis'))}")
    print('═'*70)
    print(f"  {dim('File: '+path)}")
    print(f"  {dim('Run:  '+datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print()
    print(f"  {bold(white(f'{total:,}'))} good leads loaded")
    print(f"  {bold(magenta(str(len(hv))))} high-value (20+ reviews)")

    # 1. Tier breakdown
    section("1. LEAD TIER BREAKDOWN")
    by_tier = defaultdict(list)
    for l in leads: by_tier[l['_tier']].append(l)
    max_t = max(len(v) for v in by_tier.values())
    print(f"\n  {'Tier':<18} {'Count':>6}  {'%':>5}  {'HV Leads':>9}  {'Avg Reviews':>12}  Bar")
    print('─'*70)
    for tier, items in sorted(by_tier.items(), key=lambda x: -len(x[1])):
        col   = tier_color(tier)
        hv_t  = sum(1 for l in items if l['_hv'])
        avg_r = avg(items, 'review_count')
        b     = bar(len(items), max_t, color=R if 'no_web' in tier or 'dead' in tier else Y)
        print(f"  {col(tier_label(tier).ljust(18))} {len(items):>6,}  {pct(len(items),total):>5}  {str(hv_t):>9}  {str(avg_r):>12}  {b}")

    # 2. Industry
    section("2. BREAKDOWN BY INDUSTRY")
    by_ind = defaultdict(list)
    for l in leads: by_ind[l.get('industry','Unknown')].append(l)
    rows = sorted([(ind, items) for ind, items in by_ind.items()], key=lambda x: -len(x[1]))
    max_i = max(len(v) for _, v in rows)
    print(f"\n  {'Industry':<28} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Fake':>5} {'Dead':>5} {'Avg Rev':>8} {'Avg ★':>6}  Bar")
    print('─'*70)
    for ind, items in rows:
        b = bar(len(items), max_i, width=18)
        print(f"  {white(ind[:28].ljust(28))} {len(items):>6}"
              f" {yellow(str(sum(1 for l in items if l['_hv']))):>5}"
              f" {red(str(sum(1 for l in items if l['_tier']=='no_website'))):>7}"
              f" {str(sum(1 for l in items if l['_tier']=='fake_website')):>5}"
              f" {str(sum(1 for l in items if l['_tier']=='dead_site')):>5}"
              f" {str(avg(items,'review_count')):>8}"
              f" {green(str(avg(items,'rating'))):>6}  {b}")

    # 3. City
    section("3. BREAKDOWN BY CITY")
    by_city = defaultdict(list)
    for l in leads: by_city[l.get('city','Unknown')].append(l)
    rows_c = sorted([(c, items) for c, items in by_city.items()], key=lambda x: -len(x[1]))
    max_c = max(len(v) for _, v in rows_c)
    print(f"\n  {'City':<22} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Fake':>5} {'Dead':>5} {'Avg Rev':>8}  Bar")
    print('─'*70)
    for city, items in rows_c:
        b = bar(len(items), max_c, width=20)
        print(f"  {white(city.ljust(22))} {len(items):>6}"
              f" {yellow(str(sum(1 for l in items if l['_hv']))):>5}"
              f" {red(str(sum(1 for l in items if l['_tier']=='no_website'))):>7}"
              f" {str(sum(1 for l in items if l['_tier']=='fake_website')):>5}"
              f" {str(sum(1 for l in items if l['_tier']=='dead_site')):>5}"
              f" {str(avg(items,'review_count')):>8}  {b}")

    # 4. City × Industry heatmap
    section("4. CITY × INDUSTRY  (good lead count per combo)")
    cities     = sorted(by_city.keys())
    industries = sorted(by_ind.keys())
    grid       = defaultdict(lambda: defaultdict(int))
    for l in leads: grid[l.get('city','')][l.get('industry','')] += 1
    ind_short = [i[:11] for i in industries]
    col_w = 12
    print()
    print("  " + " "*22, end="")
    for s in ind_short: print(f"{s:>{col_w}}", end="")
    print()
    print('─'*(22 + col_w*len(industries) + 2))
    for city in cities:
        print(f"  {white(city.ljust(22))}", end="")
        for industry in industries:
            val = grid[city][industry]
            if val == 0:
                print(f"{dim('—'):>{col_w}}", end="")
            else:
                col = R if val >= 15 else Y if val >= 8 else G
                print(f"{col}{val:>{col_w-1}}{RST} ", end="")
        print()

    # 5. Review distribution
    section("5. REVIEW COUNT DISTRIBUTION")
    buckets = defaultdict(list)
    for l in leads: buckets[review_bucket(l['_reviews'])].append(l)
    print(f"\n  {'Bucket':<20} {'Count':>6}  {'%':>5}  {'HV':>5}  Bar")
    print('─'*70)
    max_b = max(len(v) for v in buckets.values()) if buckets else 1
    for bucket in BUCKET_ORDER:
        items = buckets.get(bucket, [])
        hv_b  = sum(1 for l in items if l['_hv'])
        col   = R if '200+' in bucket else Y if '100' in bucket or '50' in bucket else G
        print(f"  {white(bucket.ljust(20))} {len(items):>6,}  {pct(len(items),total):>5}  {yellow(str(hv_b)):>5}  {bar(len(items),max_b,color=col)}")

    # 6. Top combos
    section("6. TOP CITY × INDUSTRY COMBOS  (by good lead count)")
    combo = defaultdict(list)
    for l in leads: combo[(l.get('city',''), l.get('industry',''))].append(l)
    combo_rows = []
    for (city, ind), items in combo.items():
        hv_c  = sum(1 for l in items if l['_hv'])
        nw_c  = sum(1 for l in items if l['_tier']=='no_website')
        avg_r = avg(items, 'review_count')
        combo_rows.append((len(items)+hv_c*2, city, ind, len(items), hv_c, nw_c, avg_r))
    combo_rows.sort(reverse=True)
    print(f"\n  {'#':<4} {'City':<20} {'Industry':<28} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Avg Rev':>8}")
    print('─'*70)
    for i, (_, city, ind, total_x, hv_c, nw_c, avg_r) in enumerate(combo_rows[:25], 1):
        col = red if i <= 3 else yellow if i <= 10 else white
        print(f"  {dim(str(i).ljust(4))} {col(city.ljust(20))} {col(ind.ljust(28))}"
              f" {total_x:>6} {yellow(str(hv_c)):>5} {red(str(nw_c)):>7} {str(avg_r):>8}")

    # 7. HV deep dive
    section("7. HIGH-VALUE LEADS DEEP DIVE  (20+ reviews)")
    print(f"\n  {bold(magenta(str(len(hv))))} high-value leads total")
    print(f"  Average reviews : {bold(str(avg(hv,'review_count')))}")
    print(f"  Average rating  : {bold(green(str(avg(hv,'rating'))))}")

    subsection("By Industry")
    hv_ind = defaultdict(list)
    for l in hv: hv_ind[l.get('industry','')].append(l)
    max_hi = max(len(v) for v in hv_ind.values()) if hv_ind else 1
    for ind, items in sorted(hv_ind.items(), key=lambda x: -len(x[1])):
        print(f"    {white(ind[:30].ljust(30))} {magenta(str(len(items)).rjust(4))}  {bar(len(items),max_hi,20,color=M)}")

    subsection("By City")
    hv_city = defaultdict(list)
    for l in hv: hv_city[l.get('city','')].append(l)
    max_hc = max(len(v) for v in hv_city.values()) if hv_city else 1
    for city, items in sorted(hv_city.items(), key=lambda x: -len(x[1])):
        print(f"    {white(city.ljust(22))} {magenta(str(len(items)).rjust(4))}  {bar(len(items),max_hc,20,color=M)}")

    subsection("Top 25 Individual High-Value Leads  (most reviews)")
    hv_sorted = sorted(hv, key=lambda x: -x['_reviews'])
    print(f"\n  {'Business':<32} {'City':<16} {'Industry':<22} {'Reviews':>8} {'Rating':>7} Tier")
    print('─'*70)
    for l in hv_sorted[:25]:
        col = tier_color(l['_tier'])
        print(f"  {white(l.get('name','')[:31].ljust(31))} {dim(l.get('city','')[:15].ljust(15))}"
              f" {dim(l.get('industry','')[:21].ljust(21))}"
              f" {yellow(str(l['_reviews']).rjust(8))} {green(str(l['_rating']).rjust(7))}"
              f" {col(tier_label(l['_tier']))}")

    # 8. Correlations
    section("8. CORRELATIONS & INSIGHTS")
    no_web = [l for l in leads if l['_tier']=='no_website']
    fake   = [l for l in leads if l['_tier']=='fake_website']
    dead   = [l for l in leads if l['_tier']=='dead_site']
    print(f"\n  {'Tier':<18} {'Avg Reviews':>12} {'Avg Rating':>11} {'% with 20+ rev':>15}")
    print('─'*70)
    for label, items in [('No Website',no_web),('Fake Website',fake),('Dead Site',dead)]:
        if not items: continue
        print(f"  {white(label.ljust(18))} {str(avg(items,'review_count')):>12}"
              f" {green(str(avg(items,'rating'))):>11}"
              f" {yellow(pct(sum(1 for l in items if l['_hv']),len(items))):>15}")

    print()
    print(f"  {bold('Industries most consistent across all cities:')}")
    ind_city = defaultdict(lambda: defaultdict(int))
    for l in leads: ind_city[l.get('industry','')][l.get('city','')] += 1
    consistency = [(ind, round(sum(v.values())/len(v),1), min(v.values()), max(v.values()))
                   for ind, v in ind_city.items()]
    consistency.sort(key=lambda x: -x[1])
    print(f"\n  {'Industry':<28} {'Avg/City':>9} {'Min':>5} {'Max':>5}")
    print('─'*70)
    for ind, avg_c, min_c, max_c in consistency:
        col = red if avg_c >= 10 else yellow if avg_c >= 6 else dim
        print(f"  {col(ind.ljust(28))} {col(str(avg_c).rjust(9))} {str(min_c):>5} {str(max_c):>5}")

    # 9. Calling strategy
    section("9. RECOMMENDED CALLING STRATEGY")
    t1 = sum(1 for l in leads if l['_tier']=='no_website'   and l['_hv'])
    t2 = sum(1 for l in leads if l['_tier']=='fake_website' and l['_hv'])
    t3 = sum(1 for l in leads if l['_tier']=='dead_site'    and l['_hv'])
    t4 = sum(1 for l in leads if not l['_hv'])
    print(f"""
  {bold(red('TIER 1 — Call first'))}
  High-value leads with no website (20+ reviews, no site)
  Count: {bold(red(str(t1)))}

  {bold(yellow('TIER 2 — Call second'))}
  High-value leads with fake websites (Facebook/Wix/X pages)
  Count: {bold(yellow(str(t2)))}

  {bold(magenta('TIER 3 — Call third'))}
  Dead sites with any reviews (site is down, customers can't find them)
  Count: {bold(magenta(str(t3)))}

  {bold(blue('TIER 4 — Fill remaining time'))}
  All remaining good leads sorted by review count descending.
  Count: {bold(blue(str(t4)))}
    """)

    print('═'*70)
    print(f"  {bold(cyan('END OF ANALYSIS'))}")
    print('═'*70)
    print()

# ══════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════

def main():
    print()
    print('═'*70)
    print(f"  {bold(cyan('LeadGen Florida — Full Pipeline'))}")
    print(f"  {dim('triage → analysis')}")
    print(f"  {dim(datetime.now().strftime('%B %d, %Y  %H:%M'))}")
    print('═'*70)

    # Resolve input
    if len(sys.argv) >= 2:
        input_csv = sys.argv[1]
    else:
        good = sorted([g for g in glob.glob("good_leads_2*.csv")
                       if 'highvalue' not in g and 'nowebsite' not in g], reverse=True)
        raw  = sorted(glob.glob("florida_raw_*.csv"), reverse=True)
        if good:
            input_csv = good[0]
        elif raw:
            input_csv = raw[0]
        else:
            print(red("  No input CSV found."))
            print(dim("  Place a florida_raw_*.csv or good_leads_*.csv in this directory,"))
            print(dim("  or pass the path as an argument: python run_pipeline.py data.csv"))
            sys.exit(1)

    import os
    is_good_leads = 'good_leads' in os.path.basename(input_csv)

    if is_good_leads:
        print(f"  {yellow('→')} Detected good_leads file — skipping triage")
        print(f"  {dim('Input: '+input_csv)}")
        run_analysis(input_csv)
    else:
        print(f"  {yellow('→')} Detected raw CSV — running full pipeline")
        print(f"  {dim('Input: '+input_csv)}")
        good_leads_path = run_triage(input_csv)
        run_analysis(good_leads_path)

if __name__ == '__main__':
    main()