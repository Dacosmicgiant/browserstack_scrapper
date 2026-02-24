# =========================================================
# elpais_scraper.py
# El País Opinion Section Scraper — BrowserStack Edition
# =========================================================
# Requirements:
#   pip install selenium requests Pillow
#
# Environment variables (set before running):
#   BROWSERSTACK_USERNAME
#   BROWSERSTACK_ACCESS_KEY
#   RAPIDAPI_KEY
# =========================================================

import os
import re
import io
import time
import json
import asyncio
import requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_URL        = "https://elpais.com/"
OPINION_URL     = "https://elpais.com/opinion/"
REMOTE_URL      = "https://hub.browserstack.com/wd/hub"
ARTICLE_LIMIT   = 5
PARALLEL_RUNS   = 5
SCROLL_ROUNDS   = 8
SCROLL_PAUSE    = 1.2
IMAGE_DIR       = Path("images")
RESULTS_DIR     = Path("output")
BUILD_NAME      = "ElPais Opinion Scraper v3"

BROWSERSTACK_USERNAME   = os.getenv("BROWSERSTACK_USERNAME")
BROWSERSTACK_ACCESS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY")
RAPIDAPI_KEY            = os.getenv("RAPIDAPI_KEY")

missing = [
    name for name, val in [
        ("BROWSERSTACK_USERNAME",   BROWSERSTACK_USERNAME),
        ("BROWSERSTACK_ACCESS_KEY", BROWSERSTACK_ACCESS_KEY),
        ("RAPIDAPI_KEY",            RAPIDAPI_KEY),
    ] if not val
]
if missing:
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# BROWSER MATRIX  (3 desktop + 2 mobile)
# =========================================================

BROWSER_MATRIX = [
    {
        "label": "Chrome-Win11",
        "browserName": "Chrome",
        "browserVersion": "latest",
        "bstack:options": {"os": "Windows", "osVersion": "11"},
    },
    {
        "label": "Firefox-Win11",
        "browserName": "Firefox",
        "browserVersion": "latest",
        "bstack:options": {"os": "Windows", "osVersion": "11"},
    },
    {
        "label": "Edge-Win11",
        "browserName": "MicrosoftEdge",
        "browserVersion": "latest",
        "bstack:options": {"os": "Windows", "osVersion": "11"},
    },
    {
        "label": "Safari-MacOS",
        "browserName": "Safari",
        "browserVersion": "17",
        "bstack:options": {"os": "OS X", "osVersion": "Sonoma"},
    },
    {
        "label": "Chrome-iPhone15",
        "browserName": "Chrome",
        "browserVersion": "latest",
        "bstack:options": {
            "deviceName": "iPhone 15",
            "osVersion": "17",
            "realMobile": "true",
        },
    },
]


# =========================================================
# CAPABILITIES BUILDER
# =========================================================

def build_capabilities(session_index: int, browser_cfg: dict) -> dict:
    bstack_base = {
        "userName":        BROWSERSTACK_USERNAME,
        "accessKey":       BROWSERSTACK_ACCESS_KEY,
        "sessionName":     f"{browser_cfg['label']} — run {session_index}",
        "buildName":       BUILD_NAME,
        "projectName":     "ElPais Opinion Scraper",
        "networkLogs":     True,
        "consoleLogs":     "warnings",
        "seleniumVersion": "4.18.1",
    }
    merged_bstack = {**bstack_base, **browser_cfg.get("bstack:options", {})}

    return {
        "browserName":    browser_cfg["browserName"],
        "browserVersion": browser_cfg.get("browserVersion", "latest"),
        "bstack:options": merged_bstack,
    }


# =========================================================
# DRIVER FACTORY
# =========================================================

def create_driver(caps: dict) -> webdriver.Remote:
    browser = caps["browserName"].lower()

    if browser == "chrome":
        options = webdriver.ChromeOptions()
    elif browser == "firefox":
        options = webdriver.FirefoxOptions()
    elif browser in ("microsoftedge", "edge"):
        options = webdriver.EdgeOptions()
    elif browser == "safari":
        options = webdriver.SafariOptions()
    else:
        options = webdriver.ChromeOptions()

    for key, value in caps.items():
        options.set_capability(key, value)

    return webdriver.Remote(command_executor=REMOTE_URL, options=options)


# =========================================================
# PAGE INTERACTION HELPERS
# =========================================================

def accept_cookies(driver: webdriver.Remote) -> None:
    selectors = [
        "button#didomi-notice-agree-button",
        "button[data-cookiebanner='accept_button']",
        "button.didomi-continue-without-agreeing",
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            btn.click()
            print("  [cookie] Banner dismissed")
            time.sleep(0.8)
            return
        except TimeoutException:
            continue
    print("  [cookie] No banner found — continuing")


def smart_scroll(driver: webdriver.Remote, rounds: int = SCROLL_ROUNDS) -> None:
    viewport_height = driver.execute_script("return window.innerHeight")
    step = max(viewport_height // 2, 400)
    for _ in range(rounds):
        driver.execute_script(f"window.scrollBy(0, {step})")
        time.sleep(SCROLL_PAUSE)
    driver.execute_script("window.scrollTo(0, 0)")
    time.sleep(0.5)


def set_spanish_locale(driver: webdriver.Remote) -> None:
    driver.execute_script(
        "Object.defineProperty(navigator, 'language', {get: () => 'es-ES'});"
    )


# =========================================================
# IMAGE HELPERS
# =========================================================

def _best_image_url(img_el) -> str:
    """
    Extract the most useful URL from an <img> element.
    Priority: data-src → data-lazy-src → srcset (first token) → src.
    Skips SVG placeholders and base64 data URIs.
    """
    if img_el is None:
        return ""

    candidates = [
        img_el.get_attribute("data-src"),
        img_el.get_attribute("data-lazy-src"),
        img_el.get_attribute("data-srcset"),
        img_el.get_attribute("srcset"),
        img_el.get_attribute("src"),
    ]

    for raw in candidates:
        if not raw:
            continue
        # srcset format: "url 1x, url 2x" — take the first URL only
        url = raw.strip().split()[0].rstrip(",")
        if url and not url.startswith("data:") and not url.endswith(".svg"):
            return url

    return ""


def _picture_source_url(element) -> str:
    """
    Look for <picture><source srcset="…"> inside an element.
    El País uses this for art-directed responsive images.
    Returns the first valid URL found, or empty string.
    """
    try:
        sources = element.find_elements(By.CSS_SELECTOR, "picture source")
        for src in sources:
            raw = (
                src.get_attribute("srcset")
                or src.get_attribute("data-srcset")
                or ""
            )
            url = raw.strip().split()[0].rstrip(",")
            if url and not url.startswith("data:") and not url.endswith(".svg"):
                return url
    except Exception:
        pass
    return ""


def fetch_og_image(driver: webdriver.Remote) -> str:
    """
    Read the og:image meta tag from the currently loaded page.
    El País sets this on every article page — it is the canonical cover image.
    Falls back to scanning <img> elements inside the article body.
    """
    try:
        og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')
        url = og.get_attribute("content") or ""
        if url and not url.startswith("data:") and not url.endswith(".svg"):
            return url
    except NoSuchElementException:
        pass

    # Secondary fallback: first substantive <img> in the article body
    for sel in ["figure.a_m img", "div.a_c img", "article img"]:
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, sel)
            for img in imgs:
                url = _best_image_url(img)
                if url:
                    return url
        except Exception:
            continue

    return ""


def download_image(image_url: str, article_index: int, label: str) -> str | None:
    """
    Download and save the cover image for an article as JPEG.
    Handles WebP and all other Pillow-supported formats.
    Returns the local file path, or None on failure.
    """
    if not image_url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ElPaisScraper/3.0)"}
        resp    = requests.get(image_url, headers=headers, timeout=20)
        resp.raise_for_status()

        img  = Image.open(io.BytesIO(resp.content)).convert("RGB")
        safe = re.sub(r"[^\w\-]", "_", label)[:40]
        path = IMAGE_DIR / f"article_{article_index:02d}_{safe}.jpg"
        img.save(path, "JPEG", quality=88)

        print(f"  [image] Saved → {path}")
        return str(path)

    except Exception as exc:
        print(f"  [image] Download failed for article {article_index}: {exc}")
        return None


# =========================================================
# ARTICLE EXTRACTION — Opinion landing page
# =========================================================

OPINION_ARTICLE_SELECTORS = [
    "section[data-dtm-region='portada_tematicos_opinion'] article",
    "section.opinion article",
    "div[data-dtm-region='opinion'] article",
    "article.opinion",
]

TITLE_SELECTORS = ["h2 a", "h3 a", "h2", "h3", ".article__title a"]

CONTENT_SELECTORS = [
    "p.article__body",
    ".article-body p",
    "div.a_c p",
    "p",
]

IMAGE_SELECTORS = [
    "figure img",
    ".article__image img",
    "img.lazy",
    "img",
]


def _find_first(element, selectors: list[str]):
    for sel in selectors:
        try:
            return element.find_element(By.CSS_SELECTOR, sel)
        except NoSuchElementException:
            continue
    return None


def extract_opinion_articles(driver: webdriver.Remote) -> list[dict]:
    """
    Navigate to the Opinion section and extract up to ARTICLE_LIMIT articles.
    Tries specific selectors first, falls back to any <article> element.
    """
    driver.get(OPINION_URL)
    set_spanish_locale(driver)
    accept_cookies(driver)
    smart_scroll(driver)

    article_elements = []
    for sel in OPINION_ARTICLE_SELECTORS:
        article_elements = driver.find_elements(By.CSS_SELECTOR, sel)
        if article_elements:
            print(f"  [extract] Found {len(article_elements)} articles via '{sel}'")
            break

    if not article_elements:
        article_elements = driver.find_elements(By.CSS_SELECTOR, "article")
        print(f"  [extract] Fallback: found {len(article_elements)} <article> elements")

    articles = []

    for idx, el in enumerate(article_elements[:ARTICLE_LIMIT]):
        try:
            # ── Title ──────────────────────────────────────────────────────
            title_el  = _find_first(el, TITLE_SELECTORS)
            title     = title_el.text.strip() if title_el else ""
            art_url   = (title_el.get_attribute("href") or "") if title_el else ""

            if not title:
                print(f"  [article {idx}] Empty title — skipping")
                continue

            # ── Content preview ────────────────────────────────────────────
            content_el = _find_first(el, CONTENT_SELECTORS)
            preview    = content_el.text.strip() if content_el else ""

            # ── Cover image — <picture><source> first, then <img> attrs ───
            image_url = _picture_source_url(el)
            if not image_url:
                img_el    = _find_first(el, IMAGE_SELECTORS)
                image_url = _best_image_url(img_el)

            articles.append({
                "index":       idx,
                "title":       title,
                "preview":     preview,
                "image_url":   image_url,
                "article_url": art_url,
            })

        except Exception as exc:
            print(f"  [article {idx}] Parse error: {exc}")
            continue

    return articles


# =========================================================
# FULL ARTICLE CONTENT — follow each article link
# =========================================================

BODY_SELECTORS = [
    "div.a_c",
    "div.article-body",
    "section.article__body",
    "div[data-dtm-region='cuerpo_articulo']",
]


def fetch_article_content(driver: webdriver.Remote, url: str) -> tuple[str, str]:
    """
    Navigate to an article page and return (body_text, og_image_url).
    og_image_url is used as a fallback when the listing had no image.
    Handles subscription walls gracefully.
    """
    if not url:
        return "(no URL available)", ""

    try:
        driver.get(url)
        accept_cookies(driver)
        smart_scroll(driver, rounds=3)

        # Always capture og:image — present on every El País article
        og_image = fetch_og_image(driver)

        for sel in BODY_SELECTORS:
            containers = driver.find_elements(By.CSS_SELECTOR, sel)
            if containers:
                paragraphs = []
                for c in containers:
                    paras = c.find_elements(By.TAG_NAME, "p")
                    paragraphs.extend(p.text.strip() for p in paras if p.text.strip())
                if paragraphs:
                    return "\n\n".join(paragraphs), og_image

        # Subscription wall or unexpected layout — return visible text
        visible = driver.find_elements(By.CSS_SELECTOR, "p")
        text    = "\n\n".join(p.text.strip() for p in visible if p.text.strip())
        clipped = text[:1500] + "…" if len(text) > 1500 else text
        return clipped, og_image

    except WebDriverException as exc:
        return f"(failed to load article: {exc})", ""


# =========================================================
# TRANSLATION  (Rapid Translate Multi Traduction API)
# =========================================================

TRANSLATE_URL = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"


def translate_to_english(texts: list[str]) -> list[str]:
    if not texts:
        return []

    payload = {"from": "es", "to": "en", "q": texts}
    headers = {
        "content-type":    "application/json",
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": "rapid-translate-multi-traduction.p.rapidapi.com",
    }

    try:
        resp = requests.post(TRANSLATE_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        # Normalise list[str] and list[list[str]] response shapes
        translated = []
        for item in result:
            translated.append(" ".join(item) if isinstance(item, list) else str(item))

        # Pad if API returned fewer items than expected
        while len(translated) < len(texts):
            translated.append(texts[len(translated)])

        return translated

    except Exception as exc:
        print(f"  [translate] API error: {exc} — using original text")
        return texts


# =========================================================
# WORD FREQUENCY ANALYSER
# =========================================================

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "it", "its", "this", "that", "as", "be", "has", "have", "do",
    "not", "no", "i", "you", "he", "she", "we", "they", "my", "your",
    "their", "our", "what", "which", "who", "when", "how", "if", "so",
    "up", "out", "into", "than", "more", "about", "also",
}


def analyse_word_frequency(titles: list[str], threshold: int = 2) -> dict[str, int]:
    """
    Count word occurrences across all translated titles.
    Returns words appearing MORE than `threshold` times, sorted by frequency.
    Stop-words and single-character tokens are excluded.
    """
    freq: dict[str, int] = {}

    for title in titles:
        words = re.findall(r"[a-záéíóúüñ']+", title.lower())
        for word in words:
            if len(word) > 1 and word not in STOP_WORDS:
                freq[word] = freq.get(word, 0) + 1

    return {w: c for w, c in sorted(freq.items(), key=lambda x: -x[1]) if c > threshold}


# =========================================================
# SINGLE BROWSERSTACK SESSION
# =========================================================

def run_session(session_index: int, browser_cfg: dict) -> dict:
    label  = browser_cfg["label"]
    caps   = build_capabilities(session_index, browser_cfg)
    driver = None

    print(f"\n[session {session_index}] Starting — {label}")

    try:
        driver      = create_driver(caps)
        session_id  = driver.session_id
        session_url = f"https://automate.browserstack.com/sessions/{session_id}.json"

        # ── Step 1: Open El País, confirm Spanish ─────────────────────────
        driver.get(BASE_URL)
        lang = driver.find_element(By.TAG_NAME, "html").get_attribute("lang") or ""
        print(f"[session {session_index}] Page language: '{lang}'")
        accept_cookies(driver)

        # ── Step 2: Scrape Opinion articles ──────────────────────────────
        articles = extract_opinion_articles(driver)
        print(f"[session {session_index}] Extracted {len(articles)} articles")

        if not articles:
            return {
                "session_index": session_index,
                "session_id":    session_id,
                "session_url":   session_url,
                "browser":       label,
                "status":        "no_data",
                "error":         "No articles extracted — selector may need updating",
                "articles":      [],
            }

        # ── Step 3: Fetch full content + images ───────────────────────────
        for art in articles:
            print(f"  → Fetching: {art['title'][:60]}")
            content, og_image = fetch_article_content(driver, art["article_url"])
            art["content"] = content

            # Use landing-page image if found; fall back to og:image
            final_image_url = art["image_url"] or og_image
            if not art["image_url"] and og_image:
                print(f"  [image] og:image fallback for: {art['title'][:40]}")

            art["image_path"] = download_image(
                final_image_url, art["index"], art["title"]
            )

        driver.execute_script(
            'browserstack_executor: {"action": "setSessionStatus", '
            '"arguments": {"status": "passed", "reason": "Scrape complete"}}'
        )

        return {
            "session_index": session_index,
            "session_id":    session_id,
            "session_url":   session_url,
            "browser":       label,
            "status":        "success",
            "articles":      articles,
        }

    except Exception as exc:
        ts         = int(time.time())
        screenshot = str(RESULTS_DIR / f"error_{session_index}_{ts}.png")

        try:
            driver.save_screenshot(screenshot)
            driver.execute_script(
                'browserstack_executor: {"action": "setSessionStatus", '
                f'"arguments": {{"status": "failed", "reason": "{exc}"}}}}'
            )
        except Exception:
            pass

        print(f"[session {session_index}] FAILED — {exc}")

        return {
            "session_index": session_index,
            "browser":       label,
            "status":        "failed",
            "error":         str(exc),
            "screenshot":    screenshot,
            "articles":      [],
        }

    finally:
        if driver:
            driver.quit()


# =========================================================
# PARALLEL RUNNER
# =========================================================

async def run_all_sessions() -> list[dict]:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=PARALLEL_RUNS) as pool:
        futures = [
            loop.run_in_executor(pool, run_session, idx, cfg)
            for idx, cfg in enumerate(BROWSER_MATRIX)
        ]
        return await asyncio.gather(*futures)


# =========================================================
# REPORTING HELPERS
# =========================================================

def print_articles(articles: list[dict]) -> None:
    print("\n" + "═" * 70)
    print("  OPINION ARTICLES  (Spanish)")
    print("═" * 70)

    for art in articles:
        print(f"\n{'─' * 70}")
        print(f"  [{art['index'] + 1}] {art['title']}")
        print(f"{'─' * 70}")
        content = art.get("content") or art.get("preview") or "(no content)"
        print(content[:400] + ("…" if len(content) > 400 else ""))
        if art.get("image_path"):
            print(f"\n  Cover image: {art['image_path']}")


def print_translations(pairs: list[tuple[str, str]]) -> None:
    print("\n" + "═" * 70)
    print("  TRANSLATED HEADERS")
    print("═" * 70)
    for es, en in pairs:
        print(f"\n  ES: {es}")
        print(f"  EN: {en}")


def print_word_frequency(freq: dict[str, int]) -> None:
    print("\n" + "═" * 70)
    print("  REPEATED WORDS IN TRANSLATED HEADERS  (count > 2)")
    print("═" * 70)

    if not freq:
        print("\n  No words appear more than twice.")
        print("  (This is expected when only 5 short headlines are analysed.)")
    else:
        for word, count in freq.items():
            print(f"  {word:<25} {count:>3}  {'█' * count}")


# =========================================================
# MAIN PIPELINE
# =========================================================

async def main() -> None:
    start = datetime.now()
    print(f"\n{'═' * 70}")
    print(f"  El País Opinion Scraper — {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 70}\n")

    # ── Parallel BrowserStack sessions ────────────────────────────────────
    results = await run_all_sessions()

    # ── Persist raw results ───────────────────────────────────────────────
    raw_path = RESULTS_DIR / "results_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results → {raw_path}")

    # ── Session summary ───────────────────────────────────────────────────
    successes = [r for r in results if r["status"] == "success"]
    no_data   = [r for r in results if r["status"] == "no_data"]
    failures  = [r for r in results if r["status"] == "failed"]

    with open(RESULTS_DIR / "failed_sessions.json", "w", encoding="utf-8") as f:
        json.dump(failures + no_data, f, indent=2, ensure_ascii=False)

    print(f"\nSession summary:")
    print(f"  Succeeded : {len(successes)}")
    print(f"  No data   : {len(no_data)}")
    print(f"  Failed    : {len(failures)}")

    # ── Deduplicate articles across sessions ──────────────────────────────
    seen: set[str]       = set()
    unique: list[dict]   = []

    for result in successes:
        for art in result["articles"]:
            if art["title"] not in seen:
                seen.add(art["title"])
                unique.append(art)
            if len(unique) == ARTICLE_LIMIT:
                break
        if len(unique) == ARTICLE_LIMIT:
            break

    print(f"\nUnique articles collected: {len(unique)}")

    if not unique:
        print("\nNo articles found. Check selectors or network access.")
        return

    # ── Step 2: Print Spanish titles + content ────────────────────────────
    print_articles(unique)

    # ── Step 3: Translate titles ──────────────────────────────────────────
    spanish_titles    = [a["title"] for a in unique]
    english_titles    = translate_to_english(spanish_titles)
    translation_pairs = list(zip(spanish_titles, english_titles))

    print_translations(translation_pairs)

    for art, en in zip(unique, english_titles):
        art["title_en"] = en

    # ── Step 4: Word frequency ────────────────────────────────────────────
    freq = analyse_word_frequency(english_titles, threshold=2)
    print_word_frequency(freq)

    # ── Persist clean output ──────────────────────────────────────────────
    clean_output = {
        "timestamp":    start.isoformat(),
        "articles":     unique,
        "translations": [{"es": es, "en": en} for es, en in translation_pairs],
        "word_freq":    freq,
        "session_summary": {
            "success": len(successes),
            "no_data": len(no_data),
            "failed":  len(failures),
        },
    }
    out_path = RESULTS_DIR / "output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clean_output, f, indent=2, ensure_ascii=False)

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'═' * 70}")
    print(f"  Done in {elapsed}s  |  Output → {out_path}")
    print(f"{'═' * 70}\n")


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())