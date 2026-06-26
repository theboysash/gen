import csv
import sys
import glob
from datetime import datetime
from collections import defaultdict

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

def bar(value, max_val, width=28, color=G):
    filled = round((value / max_val) * width) if max_val else 0
    return f"{color}{'█'*filled}{DIM}{'░'*(width-filled)}{RST}"

def pct(part, total):
    return f"{round(part/total*100)}%" if total else "0%"

def avg(items, key):
    vals = [float(x.get(key) or 0) for x in items if x.get(key) and str(x.get(key)).strip()]
    return round(sum(vals)/len(vals), 1) if vals else 0

def divider(char='─', width=70):
    print(char * width)

def section(title):
    print()
    print('═' * 70)
    print(f"  {bold(cyan(title))}")
    print('═' * 70)

def subsection(title):
    print()
    print(f"  {bold(white('── ' + title))}")
    divider()

# ── Lead quality helpers ──────────────────────────────────

def tier_color(tier):
    return {
        'no_website':   red,
        'fake_website': yellow,
        'dead_site':    magenta,
        'ssl_error':    yellow,
    }.get(tier, dim)

def tier_label(tier):
    return {
        'no_website':   'No Website',
        'fake_website': 'Fake Site',
        'dead_site':    'Dead Site',
        'ssl_error':    'SSL Error',
    }.get(tier, tier)

def review_bucket(reviews: int) -> str:
    if reviews == 0:       return '0 reviews'
    if reviews <= 9:       return '1-9 reviews'
    if reviews <= 19:      return '10-19 reviews'
    if reviews <= 49:      return '20-49 reviews'
    if reviews <= 99:      return '50-99 reviews'
    if reviews <= 199:     return '100-199 reviews'
    return '200+ reviews'

BUCKET_ORDER = [
    '0 reviews', '1-9 reviews', '10-19 reviews',
    '20-49 reviews', '50-99 reviews', '100-199 reviews', '200+ reviews'
]

# ── Main ──────────────────────────────────────────────────

def main():
    if len(sys.argv) >= 2:
        path = sys.argv[1]
    else:
        files = sorted(glob.glob("good_leads_2*.csv"), reverse=True)
        # prefer the full file not highvalue or nowebsite
        full  = [f for f in files if 'highvalue' not in f and 'nowebsite' not in f]
        if full:
            path = full[0]
        elif files:
            path = files[0]
        else:
            print(red("No good_leads_*.csv found."))
            sys.exit(1)

    with open(path, newline='', encoding='utf-8') as f:
        leads = list(csv.DictReader(f))

    for l in leads:
        l['_reviews'] = int(l.get('review_count') or 0)
        l['_rating']  = float(l.get('rating') or 0)
        l['_tier']    = l.get('lead_tier', 'unknown')
        l['_hv']      = l['_reviews'] >= 20

    total = len(leads)
    hv    = [l for l in leads if l['_hv']]

    print()
    print('═' * 70)
    print(f"  {bold(cyan('LeadGen — Good Leads Analysis'))}")
    print('═' * 70)
    print(f"  {dim('File: ' + path)}")
    print(f"  {dim('Run:  ' + datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print()
    print(f"  {bold(white(f'{total:,}'))} good leads loaded")
    print(f"  {bold(magenta(str(len(hv))))} high-value (20+ reviews)")
    print()

    # ══════════════════════════════════════════════════════
    # 1. TIER BREAKDOWN
    # ══════════════════════════════════════════════════════
    section("1. LEAD TIER BREAKDOWN")

    by_tier = defaultdict(list)
    for l in leads:
        by_tier[l['_tier']].append(l)

    max_t = max(len(v) for v in by_tier.values())
    print(f"\n  {'Tier':<18} {'Count':>6}  {'%':>5}  {'HV Leads':>9}  {'Avg Reviews':>12}  Bar")
    divider()
    for tier, items in sorted(by_tier.items(), key=lambda x: -len(x[1])):
        col   = tier_color(tier)
        hv_t  = sum(1 for l in items if l['_hv'])
        avg_r = avg(items, 'review_count')
        b     = bar(len(items), max_t, color=R if 'no_web' in tier or 'dead' in tier else Y)
        print(f"  {col(tier_label(tier).ljust(18))} {len(items):>6,}  {pct(len(items),total):>5}  {str(hv_t):>9}  {str(avg_r):>12}  {b}")

    # ══════════════════════════════════════════════════════
    # 2. BY INDUSTRY
    # ══════════════════════════════════════════════════════
    section("2. BREAKDOWN BY INDUSTRY")

    by_ind = defaultdict(list)
    for l in leads:
        by_ind[l.get('industry', 'Unknown')].append(l)

    rows = []
    for ind, items in by_ind.items():
        hv_c  = sum(1 for l in items if l['_hv'])
        nw_c  = sum(1 for l in items if l['_tier'] == 'no_website')
        fk_c  = sum(1 for l in items if l['_tier'] == 'fake_website')
        dd_c  = sum(1 for l in items if l['_tier'] == 'dead_site')
        avg_r = avg(items, 'review_count')
        avg_s = avg(items, 'rating')
        rows.append((ind, len(items), hv_c, nw_c, fk_c, dd_c, avg_r, avg_s))
    rows.sort(key=lambda x: -x[1])

    max_i = max(r[1] for r in rows)
    print(f"\n  {'Industry':<28} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Fake':>5} {'Dead':>5} {'Avg Rev':>8} {'Avg ★':>6}  Bar")
    divider()
    for ind, total_i, hv_c, nw_c, fk_c, dd_c, avg_r, avg_s in rows:
        b = bar(total_i, max_i, width=18)
        print(f"  {white(ind[:28].ljust(28))} {total_i:>6} {yellow(str(hv_c)):>5} "
              f"{red(str(nw_c)):>7} {str(fk_c):>5} {str(dd_c):>5} "
              f"{str(avg_r):>8} {green(str(avg_s)):>6}  {b}")

    # ══════════════════════════════════════════════════════
    # 3. BY CITY
    # ══════════════════════════════════════════════════════
    section("3. BREAKDOWN BY CITY")

    by_city = defaultdict(list)
    for l in leads:
        by_city[l.get('city', 'Unknown')].append(l)

    rows_c = []
    for city, items in by_city.items():
        hv_c  = sum(1 for l in items if l['_hv'])
        nw_c  = sum(1 for l in items if l['_tier'] == 'no_website')
        fk_c  = sum(1 for l in items if l['_tier'] == 'fake_website')
        dd_c  = sum(1 for l in items if l['_tier'] == 'dead_site')
        avg_r = avg(items, 'review_count')
        rows_c.append((city, len(items), hv_c, nw_c, fk_c, dd_c, avg_r))
    rows_c.sort(key=lambda x: -x[1])

    max_c = max(r[1] for r in rows_c)
    print(f"\n  {'City':<22} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Fake':>5} {'Dead':>5} {'Avg Rev':>8}  Bar")
    divider()
    for city, total_c, hv_c, nw_c, fk_c, dd_c, avg_r in rows_c:
        b = bar(total_c, max_c, width=20)
        print(f"  {white(city.ljust(22))} {total_c:>6} {yellow(str(hv_c)):>5} "
              f"{red(str(nw_c)):>7} {str(fk_c):>5} {str(dd_c):>5} "
              f"{str(avg_r):>8}  {b}")

    # ══════════════════════════════════════════════════════
    # 4. CITY × INDUSTRY HEATMAP
    # ══════════════════════════════════════════════════════
    section("4. CITY × INDUSTRY  (good lead count per combo)")

    cities     = sorted(by_city.keys())
    industries = sorted(by_ind.keys())
    grid       = defaultdict(lambda: defaultdict(int))
    for l in leads:
        grid[l.get('city','')][l.get('industry','')] = grid[l.get('city','')][l.get('industry','')] + 1

    ind_short = [i[:11] for i in industries]
    col_w = 12
    print()
    print("  " + " "*22, end="")
    for s in ind_short:
        print(f"{s:>{col_w}}", end="")
    print()
    divider(width=22 + col_w*len(industries) + 2)

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

    # ══════════════════════════════════════════════════════
    # 5. REVIEW COUNT DISTRIBUTION
    # ══════════════════════════════════════════════════════
    section("5. REVIEW COUNT DISTRIBUTION")

    buckets = defaultdict(list)
    for l in leads:
        buckets[review_bucket(l['_reviews'])].append(l)

    print(f"\n  {'Bucket':<20} {'Count':>6}  {'%':>5}  {'HV':>5}  Bar")
    divider()
    max_b = max(len(v) for v in buckets.values()) if buckets else 1
    for bucket in BUCKET_ORDER:
        items = buckets.get(bucket, [])
        hv_b  = sum(1 for l in items if l['_hv'])
        col   = R if '200+' in bucket else Y if '100' in bucket or '50' in bucket else G
        b     = bar(len(items), max_b, color=col)
        print(f"  {white(bucket.ljust(20))} {len(items):>6,}  {pct(len(items),total):>5}  {yellow(str(hv_b)):>5}  {b}")

    # ══════════════════════════════════════════════════════
    # 6. TOP CITY × INDUSTRY COMBOS
    # ══════════════════════════════════════════════════════
    section("6. TOP CITY × INDUSTRY COMBOS  (by good lead count)")

    combo = defaultdict(list)
    for l in leads:
        combo[(l.get('city',''), l.get('industry',''))].append(l)

    combo_rows = []
    for (city, ind), items in combo.items():
        hv_c  = sum(1 for l in items if l['_hv'])
        nw_c  = sum(1 for l in items if l['_tier'] == 'no_website')
        avg_r = avg(items, 'review_count')
        score = len(items) + (hv_c * 2)
        combo_rows.append((score, city, ind, len(items), hv_c, nw_c, avg_r))
    combo_rows.sort(reverse=True)

    print(f"\n  {'#':<4} {'City':<20} {'Industry':<28} {'Total':>6} {'HV':>5} {'NoSite':>7} {'Avg Rev':>8}")
    divider()
    for i, (score, city, ind, total_x, hv_c, nw_c, avg_r) in enumerate(combo_rows[:25], 1):
        col = red if i <= 3 else yellow if i <= 10 else white
        print(f"  {dim(str(i).ljust(4))} {col(city.ljust(20))} {col(ind.ljust(28))} "
              f"{total_x:>6} {yellow(str(hv_c)):>5} {red(str(nw_c)):>7} {str(avg_r):>8}")

    # ══════════════════════════════════════════════════════
    # 7. HIGH-VALUE DEEP DIVE
    # ══════════════════════════════════════════════════════
    section("7. HIGH-VALUE LEADS DEEP DIVE  (20+ reviews)")

    print(f"\n  {bold(magenta(str(len(hv))))} high-value leads total")
    print(f"  Average reviews : {bold(str(avg(hv, 'review_count')))}")
    print(f"  Average rating  : {bold(green(str(avg(hv, 'rating'))))}")

    subsection("By Industry")
    hv_ind = defaultdict(list)
    for l in hv:
        hv_ind[l.get('industry','')].append(l)
    max_hi = max(len(v) for v in hv_ind.values()) if hv_ind else 1
    for ind, items in sorted(hv_ind.items(), key=lambda x: -len(x[1])):
        b = bar(len(items), max_hi, width=20, color=M)
        print(f"    {white(ind[:30].ljust(30))} {magenta(str(len(items)).rjust(4))}  {b}")

    subsection("By City")
    hv_city = defaultdict(list)
    for l in hv:
        hv_city[l.get('city','')].append(l)
    max_hc = max(len(v) for v in hv_city.values()) if hv_city else 1
    for city, items in sorted(hv_city.items(), key=lambda x: -len(x[1])):
        b = bar(len(items), max_hc, width=20, color=M)
        print(f"    {white(city.ljust(22))} {magenta(str(len(items)).rjust(4))}  {b}")

    subsection("Top 25 Individual High-Value Leads  (most reviews)")
    hv_sorted = sorted(hv, key=lambda x: -x['_reviews'])
    print(f"\n  {'Business':<32} {'City':<16} {'Industry':<22} {'Reviews':>8} {'Rating':>7} {'Tier'}")
    divider()
    for l in hv_sorted[:25]:
        name = l.get('name','')[:31].ljust(31)
        city = l.get('city','')[:15].ljust(15)
        ind  = l.get('industry','')[:21].ljust(21)
        col  = tier_color(l['_tier'])
        print(f"  {white(name)} {dim(city)} {dim(ind)} "
              f"{yellow(str(l['_reviews']).rjust(8))} {green(str(l['_rating']).rjust(7))} "
              f"{col(tier_label(l['_tier']))}")

    # ══════════════════════════════════════════════════════
    # 8. CORRELATIONS
    # ══════════════════════════════════════════════════════
    section("8. CORRELATIONS & INSIGHTS")

    no_web  = [l for l in leads if l['_tier'] == 'no_website']
    fake    = [l for l in leads if l['_tier'] == 'fake_website']
    dead    = [l for l in leads if l['_tier'] == 'dead_site']

    print(f"\n  {'Tier':<18} {'Avg Reviews':>12} {'Avg Rating':>11} {'% with 20+ rev':>15}")
    divider()
    for label, items in [('No Website', no_web), ('Fake Website', fake), ('Dead Site', dead)]:
        if not items: continue
        avg_rev  = avg(items, 'review_count')
        avg_rat  = avg(items, 'rating')
        hv_pct   = pct(sum(1 for l in items if l['_hv']), len(items))
        print(f"  {white(label.ljust(18))} {str(avg_rev):>12} {green(str(avg_rat)):>11} {yellow(hv_pct):>15}")

    print()
    print(f"  {bold('Industries most consistent across all cities (good leads):')}")
    ind_city_counts = defaultdict(lambda: defaultdict(int))
    for l in leads:
        ind_city_counts[l.get('industry','')][l.get('city','')] += 1
    consistency = []
    for ind, city_counts in ind_city_counts.items():
        vals = list(city_counts.values())
        consistency.append((ind, round(sum(vals)/len(vals), 1), min(vals), max(vals)))
    consistency.sort(key=lambda x: -x[1])
    print(f"\n  {'Industry':<28} {'Avg/City':>9} {'Min':>5} {'Max':>5}")
    divider()
    for ind, avg_c, min_c, max_c in consistency:
        col = red if avg_c >= 10 else yellow if avg_c >= 6 else dim
        print(f"  {col(ind.ljust(28))} {col(str(avg_c).rjust(9))} {str(min_c):>5} {str(max_c):>5}")

    # ══════════════════════════════════════════════════════
    # 9. CALLING STRATEGY
    # ══════════════════════════════════════════════════════
    section("9. RECOMMENDED CALLING STRATEGY")

    print(f"""
  Based on the data, here is the optimal calling order:

  {bold(red('TIER 1 — Call first'))}
  High-value leads with no website (20+ reviews, no site)
  These businesses have proven demand and zero digital presence.
  Count: {bold(red(str(sum(1 for l in leads if l['_tier']=='no_website' and l['_hv']))))}

  {bold(yellow('TIER 2 — Call second'))}
  High-value leads with fake websites (Facebook/Wix/X pages)
  They want a web presence — they just used the wrong tool.
  Count: {bold(yellow(str(sum(1 for l in leads if l['_tier']=='fake_website' and l['_hv']))))}

  {bold(magenta('TIER 3 — Call third'))}
  Dead sites with any reviews (site is down, customers cant find them)
  Urgent problem, easy pitch: "your website is currently down".
  Count: {bold(magenta(str(sum(1 for l in leads if l['_tier']=='dead_site' and l['_hv']))))}

  {bold(blue('TIER 4 — Fill remaining time'))}
  All remaining good leads sorted by review count descending.
  Count: {bold(blue(str(sum(1 for l in leads if not l['_hv']))))}
    """)

    print('═' * 70)
    print(f"  {bold(cyan('END OF ANALYSIS'))}")
    print('═' * 70)
    print()

if __name__ == '__main__':
    main()