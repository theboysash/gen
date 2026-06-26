import asyncio
import aiohttp
import csv
import time
from datetime import datetime
from collections import defaultdict

API_KEY = "AIzaSyDt-QOkiAg8fLRi1N4eGk2GTGGHp26pByk"

INDUSTRIES = [
    "Plumbers",
    "Electricians",
    "Landscapers",
    "Cleaning companies",
    "Accountants",
    "Pest control",
    "Pool service companies",
    "Roofers",
    "HVAC companies",
    "Remodelers",
]

MARKETS = {
    "Jacksonville": [
        "San Marco Jacksonville FL",
        "Riverside Jacksonville FL",
        "Mandarin Jacksonville FL",
        "St. Johns Town Center Jacksonville FL",
        "Southside Jacksonville FL",
        "Avondale Jacksonville FL",
        "Ponte Vedra Beach FL",
        "Springfield Jacksonville FL",
        "Deerwood Jacksonville FL",
        "Oceanway Jacksonville FL",
        "Fleming Island FL",
        "Baymeadows Jacksonville FL",
        "Arlington Jacksonville FL",
        "Ortega Jacksonville FL",
        "Neptune Beach FL",
    ],
    "Orlando": [
        "Winter Park FL",
        "Lake Nona Orlando FL",
        "Baldwin Park Orlando FL",
        "Thornton Park Orlando FL",
        "Dr. Phillips Orlando FL",
        "College Park Orlando FL",
        "MetroWest Orlando FL",
        "Downtown Orlando FL",
        "Audubon Park Orlando FL",
        "Windermere FL",
        "Oviedo FL",
        "Maitland FL",
        "Altamonte Springs FL",
        "Casselberry FL",
        "Winter Garden FL",
    ],
    "Lakeland": [
        "Downtown Lakeland FL",
        "Lake Morton Lakeland FL",
        "Grasslands Lakeland FL",
        "Oakbridge Lakeland FL",
        "Dixieland Lakeland FL",
        "North Lakeland FL",
        "Mulberry FL",
        "Highland City FL",
        "Auburndale FL",
        "Winter Haven FL",
        "Bartow FL",
        "Lake Wales FL",
        "Haines City FL",
        "Davenport FL",
        "Plant City FL",
    ],
    "Fort Lauderdale": [
        "Las Olas Fort Lauderdale FL",
        "Victoria Park Fort Lauderdale FL",
        "Wilton Manors FL",
        "Cypress Creek Fort Lauderdale FL",
        "Lauderdale-by-the-Sea FL",
        "Rio Vista Fort Lauderdale FL",
        "Coral Ridge Fort Lauderdale FL",
        "Plantation FL",
        "Coral Springs FL",
        "Pompano Beach FL",
        "Deerfield Beach FL",
        "Davie FL",
        "Sunrise FL",
        "Tamarac FL",
        "Hallandale Beach FL",
    ],
    "Tampa": [
        "Westshore Tampa FL",
        "Hyde Park Tampa FL",
        "Ybor City Tampa FL",
        "Palma Ceia Tampa FL",
        "New Tampa FL",
        "Tampa Heights FL",
        "Seminole Heights Tampa FL",
        "Carrollwood Tampa FL",
        "Lutz FL",
        "Land O Lakes FL",
        "Brandon FL",
        "Riverview FL",
        "Wesley Chapel FL",
        "Valrico FL",
        "Apollo Beach FL",
    ],
    "Kissimmee": [
        "Celebration FL",
        "Poinciana FL",
        "St. Cloud FL",
        "Hunters Creek FL",
        "Buenaventura Lakes FL",
        "Downtown Kissimmee FL",
        "Reunion FL",
        "Auburndale FL",
        "BVL Kissimmee FL",
        "Narcoossee FL",
        "Intercession City FL",
        "Loughman FL",
        "Four Corners FL",
        "Harmony FL",
        "Kissimmee Bay FL",
    ],
    "West Palm Beach": [
        "Clematis Street West Palm Beach FL",
        "El Cid West Palm Beach FL",
        "Flamingo Park West Palm Beach FL",
        "Grandview Heights West Palm Beach FL",
        "Northwood Village West Palm Beach FL",
        "Palm Beach Lakes FL",
        "Southside West Palm Beach FL",
        "Palm Beach Gardens FL",
        "Jupiter FL",
        "Boynton Beach FL",
        "Delray Beach FL",
        "Boca Raton FL",
        "Wellington FL",
        "Lake Worth FL",
        "Greenacres FL",
    ],
    "St. Petersburg": [
        "EDGE District St Petersburg FL",
        "Grand Central St Petersburg FL",
        "Old Northeast St Petersburg FL",
        "Kenwood St Petersburg FL",
        "Snell Isle St Petersburg FL",
        "Gateway St Petersburg FL",
        "Tyrone St Petersburg FL",
        "Coquina Key St Petersburg FL",
        "Pinellas Park FL",
        "Largo FL",
        "Seminole FL",
        "Gulfport FL",
        "South Pasadena FL",
        "Kenneth City FL",
        "Lealman FL",
    ],
    "Clearwater": [
        "Downtown Clearwater FL",
        "Clearwater Beach FL",
        "Countryside Clearwater FL",
        "Island Estates Clearwater FL",
        "Sand Key Clearwater FL",
        "US 19 Corridor Clearwater FL",
        "Safety Harbor FL",
        "Dunedin FL",
        "Palm Harbor FL",
        "Tarpon Springs FL",
        "Oldsmar FL",
        "East Lake FL",
        "Curlew FL",
        "Belleair FL",
        "Belleair Bluffs FL",
    ],
}

CONCURRENCY = 10

R   = "\033[91m"
G   = "\033[92m"
Y   = "\033[93m"
C   = "\033[96m"
W   = "\033[97m"
DIM = "\033[2m"
BLD = "\033[1m"
RST = "\033[0m"

def red(s):    return f"{R}{s}{RST}"
def green(s):  return f"{G}{s}{RST}"
def yellow(s): return f"{Y}{s}{RST}"
def cyan(s):   return f"{C}{s}{RST}"
def white(s):  return f"{W}{s}{RST}"
def bold(s):   return f"{BLD}{s}{RST}"
def dim(s):    return f"{DIM}{s}{RST}"

def bar(value, max_val, width=22, color=G):
    filled = round((value / max_val) * width) if max_val else 0
    return f"{color}{'█'*filled}{DIM}{'░'*(width-filled)}{RST}"


async def fetch_places(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    city: str,
    area: str,
    industry: str,
    progress: dict,
) -> list:
    url     = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type":     "application/json",
        "X-Goog-Api-Key":   API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,"
            "places.rating,places.userRatingCount"
        ),
    }
    results    = []
    page_token = None

    async with semaphore:
        for page in range(2):
            body = {"textQuery": f"{industry} in {area}", "pageSize": 20}
            if page_token:
                body["pageToken"] = page_token
                await asyncio.sleep(2)

            try:
                async with session.post(
                    url, headers=headers, json=body,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    data = await resp.json()
                    if "error" in data:
                        break
                    for p in data.get("places", []):
                        results.append({
                            "city":         city,
                            "area":         area,
                            "industry":     industry,
                            "place_id":     p.get("id", ""),
                            "name":         p.get("displayName", {}).get("text", "Unknown"),
                            "address":      p.get("formattedAddress", ""),
                            "phone":        p.get("nationalPhoneNumber", ""),
                            "website":      p.get("websiteUri", ""),
                            "has_website":  "Yes" if p.get("websiteUri") else "No",
                            "rating":       p.get("rating", ""),
                            "review_count": p.get("userRatingCount", 0),
                        })
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
            except Exception as e:
                print(f"\n  {red('Error')} {area} × {industry}: {e}")
                break

    progress["done"] += 1
    done   = progress["done"]
    total  = progress["total"]
    pct    = round(done / total * 100)
    filled = round(pct / 100 * 36)
    b      = f"{G}{'█'*filled}{DIM}{'░'*(36-filled)}{RST}"
    suffix = dim(f"{done}/{total}  {area[:22]} × {industry[:14]}")
    print(f"  {b} {bold(str(pct)+'%')} {suffix}", end="\r")
    return results


async def run_scan() -> list:
    tasks_meta = [
        (city, area, industry)
        for city, areas in MARKETS.items()
        for area in areas
        for industry in INDUSTRIES
    ]

    total    = len(tasks_meta)
    progress = {"done": 0, "total": total}

    total_areas = sum(len(v) for v in MARKETS.values())
    est_min     = round(total / CONCURRENCY * 1.3 / 60, 1)

    print(f"  Cities        : {bold(str(len(MARKETS)))}")
    print(f"  Total areas   : {bold(str(total_areas))}")
    print(f"  Industries    : {bold(str(len(INDUSTRIES)))}")
    print(f"  Total queries : {bold(str(total))}")
    print(f"  Concurrency   : {bold(str(CONCURRENCY))}")
    print(f"  Est. API cost : {bold('~$' + str(round(total * 2 * 0.032, 2)))}")
    print(f"  Est. time     : {bold(str(est_min) + ' min')}")
    print()

    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks   = [
            fetch_places(session, semaphore, c, a, i, progress)
            for c, a, i in tasks_meta
        ]
        batches = await asyncio.gather(*tasks)

    print()

    # Deduplicate by place_id
    seen, unique = set(), []
    for batch in batches:
        for lead in batch:
            pid = lead["place_id"]
            if pid and pid not in seen:
                seen.add(pid)
                unique.append(lead)

    return unique


def mini_eval(leads: list):
    total    = len(leads)
    has_site = [l for l in leads if l["has_website"] == "Yes"]
    no_site  = [l for l in leads if l["has_website"] == "No"]
    hv       = [l for l in no_site if int(l.get("review_count") or 0) >= 20]

    print()
    print("═" * 70)
    print(f"  {bold(cyan('SCAN RESULTS — MINI EVALUATION'))}")
    print("═" * 70)
    print(f"  {bold(white(f'{total:,}'))} unique businesses found")
    print(f"  {green(bold(str(len(has_site))))} have a website   "
          f"{dim('('+str(round(len(has_site)/total*100))+'%)')}")
    print(f"  {red(bold(str(len(no_site))))}  have no website  "
          f"{dim('('+str(round(len(no_site)/total*100))+'%)')}")
    print(f"  {yellow(bold(str(len(hv))))}   high-value       "
          f"{dim('(no website + 20+ reviews)')}")
    print()

    # ── By industry ────────────────────────────────────────
    print(f"  {bold('BY INDUSTRY')}")
    print(f"  {'Industry':<26} {'Total':>6} {'No Site':>8} {'Rate':>6} {'HV':>5}  Bar")
    print("  " + "─" * 62)

    by_ind  = defaultdict(list)
    for l in leads:
        by_ind[l["industry"]].append(l)

    ind_rows = []
    for ind, items in by_ind.items():
        ns  = sum(1 for l in items if l["has_website"] == "No")
        hv_ = sum(1 for l in items if l["has_website"] == "No"
                  and int(l.get("review_count") or 0) >= 20)
        pct = round(ns / len(items) * 100) if items else 0
        ind_rows.append((ind, len(items), ns, pct, hv_))
    ind_rows.sort(key=lambda x: -x[3])

    max_t = max(r[1] for r in ind_rows) if ind_rows else 1
    for ind, total_i, ns, pct, hv_ in ind_rows:
        col = R if pct >= 12 else Y if pct >= 8 else G
        b   = bar(total_i, max_t, color=col)
        print(f"  {white(ind[:26].ljust(26))} {total_i:>6,} "
              f"{red(str(ns).rjust(8))} {col}{str(pct)+'%':>6}{RST} "
              f"{yellow(str(hv_).rjust(5))}  {b}")
    print()

    # ── By city ────────────────────────────────────────────
    print(f"  {bold('BY CITY')}")
    print(f"  {'City':<20} {'Total':>6} {'No Site':>8} {'Rate':>6} {'HV':>5}  Bar")
    print("  " + "─" * 62)

    by_city  = defaultdict(list)
    for l in leads:
        by_city[l["city"]].append(l)

    city_rows = []
    for city, items in by_city.items():
        ns  = sum(1 for l in items if l["has_website"] == "No")
        hv_ = sum(1 for l in items if l["has_website"] == "No"
                  and int(l.get("review_count") or 0) >= 20)
        pct = round(ns / len(items) * 100) if items else 0
        city_rows.append((city, len(items), ns, pct, hv_))
    city_rows.sort(key=lambda x: -x[3])

    max_c = max(r[1] for r in city_rows) if city_rows else 1
    for city, total_c, ns, pct, hv_ in city_rows:
        col = R if pct >= 10 else Y if pct >= 7 else G
        b   = bar(total_c, max_c, color=col)
        print(f"  {white(city.ljust(20))} {total_c:>6,} "
              f"{red(str(ns).rjust(8))} {col}{str(pct)+'%':>6}{RST} "
              f"{yellow(str(hv_).rjust(5))}  {b}")
    print()

    # ── City × Industry grid ───────────────────────────────
    print(f"  {bold('NO-WEBSITE RATE  (City × Industry)')}")
    print(f"  {'':20}", end="")
    for ind in INDUSTRIES:
        print(f"{ind[:11]:>12}", end="")
    print()
    print("  " + "─" * (20 + 12 * len(INDUSTRIES)))

    grid = defaultdict(lambda: defaultdict(list))
    for l in leads:
        grid[l["city"]][l["industry"]].append(l)

    for city, total_c, ns, pct, hv_ in city_rows:
        print(f"  {white(city.ljust(20))}", end="")
        for ind in INDUSTRIES:
            items = grid[city][ind]
            if not items:
                print(f"{dim('—'):>12}", end="")
            else:
                ns_i  = sum(1 for l in items if l["has_website"] == "No")
                pct_i = round(ns_i / len(items) * 100)
                col   = R if pct_i >= 15 else Y if pct_i >= 8 else G
                print(f"{col}{str(pct_i)+'%':>12}{RST}", end="")
        print()
    print()

    # ── Top 20 combos ──────────────────────────────────────
    print(f"  {bold('TOP 20 COMBOS  (no-website rate, min 5 businesses)')}")
    print(f"  {'#':<4} {'City':<20} {'Industry':<26} "
          f"{'Total':>6} {'No Site':>8} {'Rate':>6} {'HV':>5}")
    print("  " + "─" * 74)

    combos = []
    for city, inds in grid.items():
        for ind, items in inds.items():
            if len(items) < 5:
                continue
            ns  = sum(1 for l in items if l["has_website"] == "No")
            hv_ = sum(1 for l in items if l["has_website"] == "No"
                      and int(l.get("review_count") or 0) >= 20)
            pct = round(ns / len(items) * 100)
            opp = round(pct * 0.6 + min(hv_, 20) * 2)
            combos.append((opp, pct, city, ind, len(items), ns, hv_))
    combos.sort(reverse=True)

    for i, (opp, pct, city, ind, total_x, ns, hv_) in enumerate(combos[:20], 1):
        col = R if pct >= 15 else Y if pct >= 10 else G
        num_col = red if i <= 3 else yellow if i <= 8 else dim
        print(f"  {num_col(str(i).ljust(4))} {white(city.ljust(20))} "
              f"{ind.ljust(26)} {total_x:>6} "
              f"{red(str(ns).rjust(8))} {col}{str(pct)+'%':>6}{RST} "
              f"{yellow(str(hv_).rjust(5))}")
    print()

    # ── Top individual HV leads ────────────────────────────
    hv_leads = sorted(
        [l for l in leads if l["has_website"] == "No"
         and int(l.get("review_count") or 0) >= 20],
        key=lambda x: -int(x.get("review_count") or 0)
    )

    if hv_leads:
        print(f"  {bold('TOP 20 INDIVIDUAL HIGH-VALUE LEADS  (no website + most reviews)')}")
        print(f"  {'Business':<32} {'City':<16} {'Industry':<22} "
              f"{'Reviews':>8} {'Rating':>7}")
        print("  " + "─" * 88)
        for l in hv_leads[:20]:
            name    = l.get("name", "")[:31].ljust(31)
            city    = l.get("city", "")[:15].ljust(15)
            ind     = l.get("industry", "")[:21].ljust(21)
            reviews = int(l.get("review_count") or 0)
            rating  = l.get("rating", "")
            print(f"  {white(name)} {dim(city)} {dim(ind)} "
                  f"{yellow(str(reviews).rjust(8))} {green(str(rating).rjust(7))}")
    print()


def save_csv(leads: list, path: str):
    if not leads:
        return
    fields = ["city", "area", "industry", "name", "phone", "website",
              "has_website", "rating", "review_count", "address", "place_id"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(leads)


if __name__ == "__main__":
    print()
    print("═" * 70)
    print(f"  {bold(cyan('LeadGen — Florida Targeted Scan v2'))}")
    print(f"  {dim('10 industries · 9 cities · expanded areas')}")
    print("═" * 70)
    print(f"  {dim('Run: ' + datetime.now().strftime('%B %d, %Y %H:%M'))}")
    print()

    t0      = time.time()
    leads   = asyncio.run(run_scan())
    elapsed = round(time.time() - t0, 1)

    print(f"  {green('✓')} Scan complete in {bold(str(elapsed)+'s')}")

    mini_eval(leads)

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"florida_targeted_{ts}.csv"
    save_csv(leads, out_path)
    print(f"  {green('✓')} Saved: {bold(out_path)}")
    print()