import asyncio
import re
import time
from urllib.parse import urlparse
import os
import json
import base64
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
from playwright.async_api import async_playwright
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY")
SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

openai_client   = OpenAI(api_key=OPENAI_API_KEY)
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

ANALYSIS_TIMEOUT = 30
OPENAI_TIMEOUT   = 20

# ── Semaphore — only 1 analysis at a time ─────────────────
_semaphore = asyncio.Semaphore(1)


# ── Helpers ───────────────────────────────────────────────

def check_ssl(url: str) -> bool:
    return url.startswith("https://")


def normalise_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


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
    score  = 10

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


def upload_screenshot_sync(screenshot_bytes: bytes, url: str) -> str:
    try:
        domain   = urlparse(url).netloc.replace("www.", "").replace(".", "_")
        filename = f"{domain}_{int(time.time())}.png"

        supabase_client.storage.from_("screenshots").upload(
            filename,
            screenshot_bytes,
            {"content-type": "image/png"},
        )

        public_url = supabase_client.storage.from_("screenshots").get_public_url(filename)

        if isinstance(public_url, str):
            public_url = public_url.split("?")[0]

        logger.info(f"Screenshot uploaded: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"Screenshot upload error for {url}: {e}")
        return ""


def get_visual_score(image_b64: str, issues: list) -> dict:
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

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        max_tokens=200,
        timeout=OPENAI_TIMEOUT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}",
                        "detail": "low",
                    },
                },
            ],
        }],
    )

    raw   = response.choices[0].message.content
    clean = re.sub(r"```json|```", "", raw).strip()
    return json.loads(clean)


async def analyse(url: str) -> dict:
    url = normalise_url(url)

    result = {
        "url":               url,
        "ssl":               check_ssl(url),
        "load_time":         None,
        "mobile_responsive": False,
        "copyright_year":    None,
        "contact_info":      {},
        "meta_tags":         {},
        "screenshot_url":    "",
        "technical_score":   0,
        "visual_score":      0,
        "combined_score":    0,
        "issues":            [],
        "ai_summary":        "",
        "needs_revamp":      False,
        "error":             None,
    }

    async with _semaphore:
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                # ── Desktop load ──────────────────────────────
                context = await browser.new_context(viewport={"width": 1280, "height": 800})
                page    = await context.new_page()

                start = time.time()
                try:
                    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                except Exception as nav_err:
                    logger.warning(f"Navigation partial failure for {url}: {nav_err}")
                result["load_time"] = round(time.time() - start, 2)

                html = await page.content()
                result["copyright_year"] = extract_copyright_year(html)
                result["contact_info"]   = check_contact_info(html)
                result["meta_tags"]      = check_meta_tags(html)

                # ── Mobile check ──────────────────────────────
                try:
                    mob_ctx  = await browser.new_context(viewport={"width": 375, "height": 812})
                    mob_page = await mob_ctx.new_page()
                    await mob_page.goto(url, timeout=15000, wait_until="domcontentloaded")
                    scroll_width = await mob_page.evaluate("document.documentElement.scrollWidth")
                    result["mobile_responsive"] = scroll_width <= 390
                    await mob_ctx.close()
                except Exception as mob_err:
                    logger.warning(f"Mobile check failed for {url}: {mob_err}")
                    result["mobile_responsive"] = False

                # ── Screenshot ────────────────────────────────
                screenshot_bytes = await page.screenshot(full_page=False)
                image_b64        = base64.b64encode(screenshot_bytes).decode("utf-8")

                result["screenshot_url"] = f"data:image/png;base64,{image_b64}"

                try:
                    stored_url = upload_screenshot_sync(screenshot_bytes, url)
                    if stored_url:
                        result["screenshot_url"] = stored_url
                        logger.info(f"Also stored at: {stored_url}")
                except Exception as upload_err:
                    logger.warning(f"Storage upload failed (using base64): {upload_err}")

                await context.close()

                # ── Technical score ───────────────────────────
                tech_score, issues        = score_technical(result)
                result["technical_score"] = tech_score
                result["issues"]          = issues

                # ── OpenAI visual score ───────────────────────
                try:
                    ai = get_visual_score(image_b64, issues)
                    result["visual_score"] = ai.get("visual_score", 5)
                    result["ai_summary"]   = ai.get("summary", "")
                    result["needs_revamp"] = ai.get("needs_revamp", False)
                except Exception as ai_err:
                    logger.error(f"OpenAI scoring failed for {url}: {ai_err}")
                    result["visual_score"] = 5
                    result["ai_summary"]   = "AI analysis unavailable"
                    result["needs_revamp"] = False

                result["combined_score"] = round(
                    (result["technical_score"] + result["visual_score"]) / 2, 1
                )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Analysis error for {url}: {e}")
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    return result


# ── Routes ────────────────────────────────────────────────

@app.route("/score", methods=["GET"])
def score():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    logger.info(f"Scoring request for: {url}")

    try:
        result = asyncio.run(
            asyncio.wait_for(analyse(url), timeout=ANALYSIS_TIMEOUT)
        )
        return jsonify(result)
    except asyncio.TimeoutError:
        logger.error(f"Timeout analysing {url}")
        return jsonify({
            "url":               url,
            "error":             "Analysis timed out",
            "screenshot_url":    "",
            "technical_score":   0,
            "visual_score":      0,
            "combined_score":    0,
            "issues":            ["Analysis timed out"],
            "ai_summary":        "Could not analyse — timed out",
            "needs_revamp":      False,
            "mobile_responsive": False,
            "ssl":               check_ssl(url),
        }), 200
    except Exception as e:
        logger.error(f"Unhandled error for {url}: {e}")
        return jsonify({
            "url":               url,
            "error":             str(e),
            "screenshot_url":    "",
            "technical_score":   0,
            "visual_score":      0,
            "combined_score":    0,
            "issues":            [],
            "ai_summary":        "Could not analyse",
            "needs_revamp":      False,
            "mobile_responsive": False,
            "ssl":               check_ssl(url),
        }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)