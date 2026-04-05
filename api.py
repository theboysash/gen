import asyncio
import base64
import re
import time
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from flask_cors import CORS
from playwright.async_api import async_playwright
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
CORS(app)


# ── Helpers ───────────────────────────────────────────────

def check_ssl(url: str) -> bool:
    return url.startswith("https://")

def extract_copyright_year(html: str):
    matches = re.findall(r"©\s*(\d{4})|copyright\s*(\d{4})", html, re.IGNORECASE)
    years = [int(y) for pair in matches for y in pair if y]
    return min(years) if years else None

def check_contact_info(html: str) -> dict:
    return {
        "form":  bool(re.search(r"<form[\s>]", html, re.IGNORECASE)),
        "phone": bool(re.search(r"(\+27|0)[0-9\s\-]{8,12}", html)),
        "email": bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)),
    }

def check_meta_tags(html: str) -> dict:
    return {
        "title":     bool(re.search(r"<title>[^<]{5,}</title>", html, re.IGNORECASE)),
        "meta_desc": bool(re.search(r'<meta[^>]+name=["\']description["\']', html, re.IGNORECASE)),
        "viewport":  bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE)),
    }

def score_technical(checks: dict):
    issues = []
    score = 10

    if not checks["ssl"]:
        score -= 2
        issues.append("No SSL — browsers show 'Not Secure' to visitors")

    if not checks["mobile_responsive"]:
        score -= 2
        issues.append("Not mobile responsive")

    year = checks["copyright_year"]
    if year:
        age = 2026 - year
        if age >= 5:
            score -= 2
            issues.append(f"Copyright year {year} — site is {age} years old")
        elif age >= 3:
            score -= 1
            issues.append(f"Copyright year {year} — possibly outdated")

    contact = checks["contact_info"]
    if not any(contact.values()):
        score -= 2
        issues.append("No contact info found")
    elif not contact["form"] and not contact["phone"]:
        score -= 1
        issues.append("No contact form or phone number visible")

    meta = checks["meta_tags"]
    if not meta["title"] or not meta["meta_desc"]:
        score -= 1
        issues.append("Missing SEO meta tags")

    if checks["load_time"] and checks["load_time"] > 5:
        score -= 1
        issues.append(f"Slow load time ({checks['load_time']:.1f}s)")

    return max(score, 0), issues


async def analyse(url: str) -> dict:
    result = {
        "url": url,
        "ssl": check_ssl(url),
        "load_time": None,
        "mobile_responsive": False,
        "copyright_year": None,
        "contact_info": {},
        "meta_tags": {},
        "screenshot_base64": None,
        "technical_score": 0,
        "visual_score": 0,
        "combined_score": 0,
        "issues": [],
        "ai_summary": "",
        "needs_revamp": False,
        "error": None,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            # ── Desktop load ──────────────────────────────
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()

            start = time.time()
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            result["load_time"] = round(time.time() - start, 2)

            html = await page.content()
            result["copyright_year"] = extract_copyright_year(html)
            result["contact_info"]   = check_contact_info(html)
            result["meta_tags"]      = check_meta_tags(html)

            # ── Mobile check ──────────────────────────────
            mob_ctx = await browser.new_context(viewport={"width": 375, "height": 812})
            mob_page = await mob_ctx.new_page()
            await mob_page.goto(url, timeout=15000, wait_until="domcontentloaded")
            scroll_width = await mob_page.evaluate("document.documentElement.scrollWidth")
            result["mobile_responsive"] = scroll_width <= 390
            await mob_ctx.close()

            # ── Screenshot ────────────────────────────────
            screenshot_bytes = await page.screenshot(full_page=False)
            result["screenshot_base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
            await context.close()

            # ── Technical score ───────────────────────────
            tech_score, issues = score_technical(result)
            result["technical_score"] = tech_score
            result["issues"] = issues

            # ── OpenAI visual score ───────────────────────
            issues_text = "\n".join(f"- {i}" for i in issues) if issues else "None"
            prompt = f"""You are evaluating a small business website for a web design agency.

Technical issues already detected:
{issues_text}

Rate the visual design and respond ONLY with valid JSON, no markdown:
{{
  "visual_score": <integer 1-10>,
  "summary": "<one sentence on the biggest problem or strength>",
  "needs_revamp": <true or false>
}}"""

            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{result['screenshot_base64']}",
                                    "detail": "low"
                                }
                            }
                        ]
                    }
                ]
            )

            raw = response.choices[0].message.content
            clean = re.sub(r"```json|```", "", raw).strip()

            import json
            ai = json.loads(clean)
            result["visual_score"]  = ai.get("visual_score", 0)
            result["ai_summary"]    = ai.get("summary", "")
            result["needs_revamp"]  = ai.get("needs_revamp", False)
            result["combined_score"] = round((tech_score + result["visual_score"]) / 2, 1)

        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()

    return result


# ── Route ─────────────────────────────────────────────────

@app.route("/score", methods=["GET"])
def score():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        result = asyncio.run(analyse(url))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True, use_reloader=False)