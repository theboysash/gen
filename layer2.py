import asyncio
import base64
import csv
import json
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from playwright.async_api import async_playwright

OPENAI_API_KEY = "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"

# ── Helpers ───────────────────────────────────────────────

def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def check_ssl(url: str) -> bool:
    return url.startswith("https://")


def extract_copyright_year(html: str) -> int | None:
    matches = re.findall(r"©\s*(\d{4})|copyright\s*(\d{4})", html, re.IGNORECASE)
    years = [int(y) for pair in matches for y in pair if y]
    return min(years) if years else None


def check_contact_info(html: str) -> dict:
    has_form = bool(re.search(r"<form[\s>]", html, re.IGNORECASE))
    has_phone = bool(re.search(r"(\+27|0)[0-9\s\-]{8,12}", html))
    has_email = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html))
    return {"form": has_form, "phone": has_phone, "email": has_email}


def check_meta_tags(html: str) -> dict:
    has_title = bool(re.search(r"<title>[^<]{5,}</title>", html, re.IGNORECASE))
    has_meta_desc = bool(re.search(r'<meta[^>]+name=["\']description["\']', html, re.IGNORECASE))
    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE))
    return {"title": has_title, "meta_desc": has_meta_desc, "viewport": has_viewport}


def score_technical(checks: dict) -> tuple[int, list[str]]:
    """
    Score technical checks out of 10, return score + list of issues found.
    """
    issues = []
    score = 10

    if not checks["ssl"]:
        score -= 2
        issues.append("No SSL (site shows as 'Not Secure' to visitors)")

    if not checks["mobile_responsive"]:
        score -= 2
        issues.append("Not mobile responsive")

    year = checks["copyright_year"]
    if year:
        age = datetime.now().year - year
        if age >= 5:
            score -= 2
            issues.append(f"Copyright year {year} — site is {age} years old")
        elif age >= 3:
            score -= 1
            issues.append(f"Copyright year {year} — possibly outdated")

    contact = checks["contact_info"]
    if not contact["form"] and not contact["phone"] and not contact["email"]:
        score -= 2
        issues.append("No contact info found (no form, phone, or email)")
    elif not contact["form"] and not contact["phone"]:
        score -= 1
        issues.append("No contact form or phone number visible")

    meta = checks["meta_tags"]
    if not meta["title"] or not meta["meta_desc"]:
        score -= 1
        issues.append("Missing SEO meta tags (title/description)")

    if checks["load_time"] > 5:
        score -= 1
        issues.append(f"Slow load time ({checks['load_time']:.1f}s)")

    return max(score, 0), issues


async def score_visual_with_openai(screenshot_bytes: bytes, technical_issues: list[str]) -> dict:
    """
    Send screenshot to OpenAI GPT-4 Vision for visual quality scoring.
    """
    image_b64 = encode_image(screenshot_bytes)
    issues_text = "\n".join(f"- {i}" for i in technical_issues) if technical_issues else "None found"

    prompt = f"""You are evaluating a small business website for a web design agency.

Technical issues already detected by code:
{issues_text}

Look at this screenshot and evaluate:
1. Visual design quality (modern vs outdated aesthetic)
2. Layout clarity and professionalism
3. Whether it looks trustworthy to a potential customer

Respond ONLY with a JSON object in this exact format, no other text:
{{
  "visual_score": <integer 1-10>,
  "summary": "<one sentence describing the biggest visual problem or strength>",
  "needs_revamp": <true or false>
}}"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "gpt-4o",
        "max_tokens": 200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=body
    )

    result = response.json()

    try:
        content = result["choices"][0]["message"]["content"]
        # Strip markdown fences if present
        clean = re.sub(r"```json|```", "", content).strip()
        return json.loads(clean)
    except Exception as e:
        print(f"  OpenAI parse error: {e} | Raw: {result}")
        return {"visual_score": 0, "summary": "Could not evaluate", "needs_revamp": False}


async def analyse_website(url: str, playwright) -> dict:
    """
    Full analysis of a single website — technical checks + screenshot + AI scoring.
    """
    result = {
        "url": url,
        "ssl": check_ssl(url),
        "load_time": None,
        "mobile_responsive": False,
        "copyright_year": None,
        "contact_info": {},
        "meta_tags": {},
        "screenshot_path": None,
        "technical_score": 0,
        "visual_score": 0,
        "combined_score": 0,
        "issues": [],
        "ai_summary": "",
        "needs_revamp": False,
        "error": None
    }

    browser = await playwright.chromium.launch(headless=True)

    try:
        # ── Desktop load ──────────────────────────────────
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        start = time.time()
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        result["load_time"] = round(time.time() - start, 2)

        html = await page.content()
        result["copyright_year"] = extract_copyright_year(html)
        result["contact_info"] = check_contact_info(html)
        result["meta_tags"] = check_meta_tags(html)

        # ── Mobile responsiveness check ───────────────────
        mobile_context = await browser.new_context(viewport={"width": 375, "height": 812})
        mobile_page = await mobile_context.new_page()
        await mobile_page.goto(url, timeout=15000, wait_until="domcontentloaded")

        # Check if horizontal scrollbar appears (sign of non-responsive layout)
        scroll_width = await mobile_page.evaluate("document.documentElement.scrollWidth")
        result["mobile_responsive"] = scroll_width <= 390
        await mobile_context.close()

        # ── Screenshot (desktop) ──────────────────────────
        screenshot_bytes = await page.screenshot(full_page=False)
        domain = urlparse(url).netloc.replace("www.", "")
        screenshot_path = f"screenshots/{domain}.png"

        import os
        os.makedirs("screenshots", exist_ok=True)
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        result["screenshot_path"] = screenshot_path

        await context.close()

        # ── Technical scoring ─────────────────────────────
        tech_score, issues = score_technical(result)
        result["technical_score"] = tech_score
        result["issues"] = issues

        # ── AI visual scoring ─────────────────────────────
        print(f"  Sending to OpenAI for visual scoring...")
        ai = await score_visual_with_openai(screenshot_bytes, issues)
        result["visual_score"] = ai.get("visual_score", 0)
        result["ai_summary"] = ai.get("summary", "")
        result["needs_revamp"] = ai.get("needs_revamp", False)

        # Combined score — equal weight
        result["combined_score"] = round((tech_score + result["visual_score"]) / 2, 1)

    except Exception as e:
        result["error"] = str(e)
        print(f"  Error: {e}")
    finally:
        await browser.close()

    return result


async def score_leads(input_csv: str, output_csv: str):
    """
    Read leads CSV, score each website, write enriched CSV.
    """
    # Read leads
    with open(input_csv, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    # Filter to only leads that have a website
    with_website = [l for l in leads if l.get("website")]
    without_website = [l for l in leads if not l.get("website")]

    print(f"\nLeads with website    : {len(with_website)}")
    print(f"Leads without website : {len(without_website)} (instant leads — no site at all)")
    print(f"\nScoring {len(with_website)} websites...\n")

    results = []

    async with async_playwright() as playwright:
        for i, lead in enumerate(with_website):
            url = lead["website"]
            print(f"[{i+1}/{len(with_website)}] {lead['name']} | {url}")

            analysis = await analyse_website(url, playwright)

            enriched = {**lead, **{
                "ssl":               "Yes" if analysis["ssl"] else "No",
                "load_time_s":       analysis["load_time"],
                "mobile_responsive": "Yes" if analysis["mobile_responsive"] else "No",
                "copyright_year":    analysis["copyright_year"] or "",
                "has_contact":       "Yes" if any(analysis["contact_info"].values()) else "No",
                "technical_score":   analysis["technical_score"],
                "visual_score":      analysis["visual_score"],
                "combined_score":    analysis["combined_score"],
                "needs_revamp":      "Yes" if analysis["needs_revamp"] else "No",
                "issues":            " | ".join(analysis["issues"]),
                "ai_summary":        analysis["ai_summary"],
                "screenshot":        analysis["screenshot_path"] or "",
                "error":             analysis["error"] or "",
            }}
            results.append(enriched)

            # Small delay between sites to be polite
            await asyncio.sleep(1)

    # Add no-website leads back (they score 0 by default — easiest targets)
    for lead in without_website:
        enriched = {**lead, **{
            "ssl": "", "load_time_s": "", "mobile_responsive": "",
            "copyright_year": "", "has_contact": "",
            "technical_score": 0, "visual_score": 0, "combined_score": 0,
            "needs_revamp": "Yes",
            "issues": "No website at all",
            "ai_summary": "No website — highest priority lead",
            "screenshot": "", "error": ""
        }}
        results.append(enriched)

    # Sort by combined score ascending (worst sites first = best leads first)
    results.sort(key=lambda x: float(x["combined_score"]) if x["combined_score"] != "" else -1)

    # Write output
    if results:
        fieldnames = list(results[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    print(f"\nDone. Scored {len(results)} leads.")
    print(f"Results saved to: {output_csv}")
    print(f"Sorted by combined score — worst sites at the top.")


# ── Entry point ───────────────────────────────────────────
if __name__ == "__main__":
    INPUT_CSV  = "leads_dentist_sandton_20260403_173205.csv"  # your leads file
    OUTPUT_CSV = "scored_leads.csv"

    asyncio.run(score_leads(INPUT_CSV, OUTPUT_CSV))