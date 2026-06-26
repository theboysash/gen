import csv
import sys
from collections import defaultdict
from datetime import datetime

# ── Load CSV ──────────────────────────────────────────────

def load_csv(path: str) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ── Helpers ───────────────────────────────────────────────

def pct(part, total):
    return f"{round(part/total*100)}%" if total else "0%"

def avg_rating(items):
    ratings = [float(x["rating"]) for x in items if x.get("rating") and x["rating"] != ""]
    return round(sum(ratings)/len(ratings), 2) if ratings else 0

def no_site(items):
    return [x for x in items if x.get("has_website") == "No"]

def high_value(items):
    return [x for x in no_site(items) if int(x.get("review_count") or 0) >= 20]

def divider(char="─", width=70):
    print(char * width)

def section(title):
    print()
    divider("═")
    print(f"  {title}")
    divider("═")

def subsection(title):
    print(f"\n  ── {title}")
    divider()

# ── Analysis Functions ────────────────────────────────────

def overall_summary(leads):
    section("OVERALL SUMMARY")
    total    = len(leads)
    no_web   = no_site(leads)
    hv       = high_value(leads)
    has_web  = [x for x in leads if x.get("has_website") == "Yes"]

    print(f"\n  Total businesses scanned   : {total:,}")
    print(f"  Have a website             : {len(has_web):,}  ({pct(len(has_web), total)})")
    print(f"  No website                 : {len(no_web):,}  ({pct(len(no_web), total)})")
    print(f"  High-value leads           : {len(hv):,}  ({pct(len(hv), total)})  ← no website + 20+ reviews")
    print(f"  Average Google rating      : {avg_rating(leads)}")

    cities     = len(set(x["city"] for x in leads))
    industries = len(set(x["industry"] for x in leads))
    areas      = len(set(x["area"] for x in leads))
    print(f"\n  Cities covered             : {cities}")
    print(f"  Areas covered              : {areas}")
    print(f"  Industries covered         : {industries}")


def by_city(leads):
    section("BREAKDOWN BY CITY")
    grouped = defaultdict(list)
    for l in leads:
        grouped[l["city"]].append(l)

    rows = []
    for city, items in grouped.items():
        nw = no_site(items)
        hv = high_value(items)
        rows.append((city, len(items), len(nw), pct(len(nw), len(items)),
                     len(hv), avg_rating(items)))

    rows.sort(key=lambda x: int(x[3].replace("%","")), reverse=True)

    print(f"\n  {'City':<22} {'Total':>6} {'No Site':>8} {'%':>6} {'High Val':>9} {'Avg ★':>7}")
    divider()
    for city, total, nw, p, hv, ar in rows:
        print(f"  {city:<22} {total:>6,} {nw:>8,} {p:>6} {hv:>9,} {ar:>7}")


def by_industry(leads):
    section("BREAKDOWN BY INDUSTRY")
    grouped = defaultdict(list)
    for l in leads:
        grouped[l["industry"]].append(l)

    rows = []
    for ind, items in grouped.items():
        nw = no_site(items)
        hv = high_value(items)
        rows.append((ind, len(items), len(nw), pct(len(nw), len(items)),
                     len(hv), avg_rating(items)))

    rows.sort(key=lambda x: int(x[3].replace("%","")), reverse=True)

    print(f"\n  {'Industry':<30} {'Total':>6} {'No Site':>8} {'%':>6} {'High Val':>9} {'Avg ★':>7}")
    divider()
    for ind, total, nw, p, hv, ar in rows:
        print(f"  {ind:<30} {total:>6,} {nw:>8,} {p:>6} {hv:>9,} {ar:>7}")


def by_area(leads):
    section("BREAKDOWN BY AREA  (top 20 by no-website %)")
    grouped = defaultdict(list)
    for l in leads:
        grouped[l["area"]].append(l)

    rows = []
    for area, items in grouped.items():
        nw = no_site(items)
        hv = high_value(items)
        city = items[0]["city"]
        rows.append((area, city, len(items), len(nw),
                     int(pct(len(nw), len(items)).replace("%","")),
                     len(hv), avg_rating(items)))

    rows.sort(key=lambda x: x[4], reverse=True)

    print(f"\n  {'Area':<30} {'City':<16} {'Total':>6} {'No Site':>8} {'%':>6} {'High Val':>9}")
    divider()
    for area, city, total, nw, p, hv, ar in rows[:20]:
        print(f"  {area:<30} {city:<16} {total:>6,} {nw:>8,} {p:>5}% {hv:>9,}")


def city_x_industry(leads):
    section("CITY × INDUSTRY HEATMAP  (no-website %)")

    cities     = sorted(set(x["city"] for x in leads))
    industries = sorted(set(x["industry"] for x in leads))

    grouped = defaultdict(lambda: defaultdict(list))
    for l in leads:
        grouped[l["city"]][l["industry"]].append(l)

    # Print header
    ind_short = [i[:14] for i in industries]
    col_w = 15
    print("\n  " + " " * 22, end="")
    for s in ind_short:
        print(f"{s:>{col_w}}", end="")
    print()
    divider(width=22 + col_w * len(industries) + 2)

    for city in cities:
        print(f"  {city:<22}", end="")
        for industry in industries:
            items = grouped[city][industry]
            if not items:
                print(f"{'—':>{col_w}}", end="")
            else:
                nw = len(no_site(items))
                p  = round(nw / len(items) * 100)
                print(f"{p:>{col_w-1}}%", end="")
        print()


def top_opportunities(leads, n=20):
    section(f"TOP {n} OPPORTUNITIES  (city + industry combos)")

    grouped = defaultdict(list)
    for l in leads:
        key = (l["city"], l["industry"])
        grouped[key].append(l)

    rows = []
    for (city, ind), items in grouped.items():
        nw  = len(no_site(items))
        hv  = len(high_value(items))
        p   = round(nw / len(items) * 100) if items else 0
        opp = round((p * 0.6) + (min(hv, 20) * 2))
        rows.append((opp, city, ind, len(items), nw, p, hv))

    rows.sort(reverse=True)

    print(f"\n  {'#':<4} {'City':<20} {'Industry':<28} {'Total':>6} {'No Site':>8} {'%':>6} {'HV':>5} {'Score':>6}")
    divider()
    for i, (opp, city, ind, total, nw, p, hv) in enumerate(rows[:n], 1):
        print(f"  {i:<4} {city:<20} {ind:<28} {total:>6,} {nw:>8,} {p:>5}% {hv:>5} {opp:>6}")


def high_value_deep_dive(leads):
    section("HIGH-VALUE LEADS DEEP DIVE  (no website + 20+ reviews)")

    hv_leads = high_value(leads)
    print(f"\n  Total high-value leads: {len(hv_leads):,}")

    # By city
    subsection("By City")
    by_city_hv = defaultdict(list)
    for l in hv_leads:
        by_city_hv[l["city"]].append(l)
    rows = sorted(by_city_hv.items(), key=lambda x: len(x[1]), reverse=True)
    for city, items in rows:
        print(f"    {city:<22} {len(items):>5,} leads")

    # By industry
    subsection("By Industry")
    by_ind_hv = defaultdict(list)
    for l in hv_leads:
        by_ind_hv[l["industry"]].append(l)
    rows = sorted(by_ind_hv.items(), key=lambda x: len(x[1]), reverse=True)
    for ind, items in rows:
        print(f"    {ind:<30} {len(items):>5,} leads")

    # Top individual high-value leads
    subsection("Top 20 Individual High-Value Leads  (most reviews, no website)")
    sorted_hv = sorted(hv_leads, key=lambda x: int(x.get("review_count") or 0), reverse=True)
    print(f"\n    {'Business':<35} {'City':<16} {'Industry':<22} {'Reviews':>8} {'Rating':>7}")
    divider(width=95)
    for l in sorted_hv[:20]:
        name = l["name"][:34]
        print(f"    {name:<35} {l['city']:<16} {l['industry']:<22} "
              f"{int(l.get('review_count') or 0):>8,} {l.get('rating',''):>7}")


def review_count_analysis(leads):
    section("REVIEW COUNT ANALYSIS  (no-website businesses only)")

    nw = no_site(leads)
    buckets = {
        "0 reviews":      [x for x in nw if int(x.get("review_count") or 0) == 0],
        "1–9 reviews":    [x for x in nw if 1  <= int(x.get("review_count") or 0) <= 9],
        "10–19 reviews":  [x for x in nw if 10 <= int(x.get("review_count") or 0) <= 19],
        "20–49 reviews":  [x for x in nw if 20 <= int(x.get("review_count") or 0) <= 49],
        "50–99 reviews":  [x for x in nw if 50 <= int(x.get("review_count") or 0) <= 99],
        "100–199 reviews":[x for x in nw if 100<= int(x.get("review_count") or 0) <= 199],
        "200+ reviews":   [x for x in nw if int(x.get("review_count") or 0) >= 200],
    }

    print(f"\n  Businesses with NO website broken down by review count:\n")
    total_nw = len(nw)
    for label, items in buckets.items():
        bar = "█" * round(len(items) / max(len(b) for b in buckets.values()) * 30)
        print(f"  {label:<18} {len(items):>5,}  {pct(len(items), total_nw):>5}  {bar}")


def correlations(leads):
    section("CORRELATIONS & INSIGHTS")

    nw      = no_site(leads)
    has_web = [x for x in leads if x.get("has_website") == "Yes"]

    avg_reviews_nw  = sum(int(x.get("review_count") or 0) for x in nw) / len(nw) if nw else 0
    avg_reviews_hw  = sum(int(x.get("review_count") or 0) for x in has_web) / len(has_web) if has_web else 0
    avg_rating_nw   = avg_rating(nw)
    avg_rating_hw   = avg_rating(has_web)

    print(f"\n  Businesses WITH a website:")
    print(f"    Average reviews : {avg_reviews_hw:.1f}")
    print(f"    Average rating  : {avg_rating_hw}")

    print(f"\n  Businesses WITHOUT a website:")
    print(f"    Average reviews : {avg_reviews_nw:.1f}")
    print(f"    Average rating  : {avg_rating_nw}")

    print(f"\n  Insight: Businesses without websites have "
          f"{'more' if avg_reviews_nw > avg_reviews_hw else 'fewer'} reviews on average "
          f"({avg_reviews_nw:.1f} vs {avg_reviews_hw:.1f})")
    print(f"  Insight: Businesses without websites have "
          f"{'higher' if avg_rating_nw > avg_rating_hw else 'lower'} ratings on average "
          f"({avg_rating_nw} vs {avg_rating_hw})")

    # Industry correlation: which industries most consistently lack websites across ALL cities
    print(f"\n  Industries most consistently lacking websites across all cities:")
    grouped = defaultdict(lambda: defaultdict(list))
    for l in leads:
        grouped[l["industry"]][l["city"]].append(l)

    consistency = []
    for ind, cities in grouped.items():
        city_pcts = []
        for city, items in cities.items():
            nw_c = len(no_site(items))
            city_pcts.append(round(nw_c / len(items) * 100) if items else 0)
        avg_pct  = round(sum(city_pcts) / len(city_pcts))
        min_pct  = min(city_pcts)
        consistency.append((ind, avg_pct, min_pct, len(city_pcts)))

    consistency.sort(key=lambda x: x[1], reverse=True)
    print(f"\n    {'Industry':<30} {'Avg %':>7} {'Min %':>7}  (across all cities)")
    divider(width=55)
    for ind, avg_p, min_p, cities_count in consistency:
        print(f"    {ind:<30} {avg_p:>6}% {min_p:>6}%")


def recommended_starting_points(leads):
    section("RECOMMENDED STARTING POINTS FOR MOHAMMED")

    grouped = defaultdict(list)
    for l in leads:
        key = (l["city"], l["industry"])
        grouped[key].append(l)

    rows = []
    for (city, ind), items in grouped.items():
        nw  = len(no_site(items))
        hv  = len(high_value(items))
        p   = round(nw / len(items) * 100) if items else 0
        opp = round((p * 0.6) + (min(hv, 20) * 2))
        rows.append((opp, city, ind, len(items), nw, p, hv))

    rows.sort(reverse=True)
    top3 = rows[:3]

    print("\n  Based on opportunity score (no-website rate + high-value lead density):\n")
    for i, (opp, city, ind, total, nw, p, hv) in enumerate(top3, 1):
        print(f"  #{i}  {ind} in {city}")
        print(f"       Score: {opp}  |  {nw}/{total} have no website ({p}%)  |  {hv} high-value leads")
        print()

    print("  These three combos represent the highest density of businesses")
    print("  that (a) have proven customer demand via reviews and (b) have")
    print("  no digital presence to compete with.")


# ── Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Try to find the most recent CSV automatically
        import glob
        csvs = sorted(glob.glob("florida_raw_*.csv"), reverse=True)
        if not csvs:
            print("Usage: python florida_analysis.py florida_raw_TIMESTAMP.csv")
            sys.exit(1)
        path = csvs[0]
        print(f"Auto-detected: {path}")
    else:
        path = sys.argv[1]

    print(f"\nLeadGen Florida Market Analysis")
    print(f"File: {path}")
    print(f"Run:  {datetime.now().strftime('%B %d, %Y %H:%M')}")

    leads = load_csv(path)

    overall_summary(leads)
    by_city(leads)
    by_industry(leads)
    by_area(leads)
    top_opportunities(leads)
    high_value_deep_dive(leads)
    review_count_analysis(leads)
    correlations(leads)
    recommended_starting_points(leads)

    print()
    divider("═")
    print("  END OF REPORT")
    divider("═")
    print()