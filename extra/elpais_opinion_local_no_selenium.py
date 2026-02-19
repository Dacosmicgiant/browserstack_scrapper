import os
import re
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from collections import Counter
from urllib.parse import urljoin
from dotenv import load_dotenv

# =========================================================
# ENV
# =========================================================
load_dotenv()

BASE_URL = "https://elpais.com"
TRANSLATE_URL = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

if not RAPIDAPI_KEY:
    raise ValueError("RAPIDAPI_KEY missing in .env")

HEADERS_TRANSLATE = {
    "content-type": "application/json",
    "x-rapidapi-host": "rapid-translate-multi-traduction.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY,
}

CONCURRENT_REQUESTS = 5
TIMEOUT = aiohttp.ClientTimeout(total=30)

# =========================================================
# 1️⃣ GET OPINION LINKS FROM HOMEPAGE SECTION
# =========================================================
def get_opinion_links(limit=5):

    print("Fetching homepage HTML...")
    html = requests.get(BASE_URL, timeout=15).text
    soup = BeautifulSoup(html, "lxml")

    section = soup.select_one(
        "section[data-dtm-region='portada_tematicos_opinion']"
    )

    if not section:
        raise RuntimeError("Opinion section not found")

    anchors = section.select("a[href]")
    links = []

    for a in anchors:
        href = a["href"]

        # only real opinion articles
        if re.search(r"/opinion/\d{4}-\d{2}-\d{2}/", href):
            links.append(href)

    # remove duplicates
    unique = list(dict.fromkeys(links))

    return unique[:limit]


# =========================================================
# 2️⃣ FETCH ARTICLE PAGE
# =========================================================
async def fetch_article(session, url):

    async with session.get(url) as resp:
        resp.raise_for_status()
        html = await resp.text()

    soup = BeautifulSoup(html, "lxml")

    title = soup.find("h1")
    title = title.get_text(strip=True) if title else "NO TITLE"

    paragraphs = soup.select("article p")
    content = "\n".join(p.get_text(strip=True) for p in paragraphs)

    img = soup.select_one("figure img")
    img_url = None
    if img and img.get("src"):
        img_url = urljoin(url, img["src"])

    return {
        "url": url,
        "title": title,
        "content": content,
        "image": img_url
    }


# =========================================================
# 3️⃣ DOWNLOAD IMAGE
# =========================================================
async def download_image(session, url, filename):
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()

        with open(filename, "wb") as f:
            f.write(data)

        print("Saved image:", filename)

    except Exception as e:
        print("Image download failed:", e)


# =========================================================
# 4️⃣ TRANSLATE TITLES
# =========================================================
async def translate_titles(session, titles):

    payload = {
        "from": "es",
        "to": "en",
        "q": titles
    }

    async with session.post(
        TRANSLATE_URL,
        json=payload,
        headers=HEADERS_TRANSLATE
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()

    return data


# =========================================================
# 5️⃣ WORD FREQUENCY ANALYSIS
# =========================================================
def repeated_words(texts):

    words = []
    for t in texts:
        tokens = re.findall(r"[a-zA-Z']+", t.lower())
        words.extend(tokens)

    counts = Counter(words)
    return {w: c for w, c in counts.items() if c > 2}


# =========================================================
# 6️⃣ MAIN PIPELINE
# =========================================================
async def main():

    print("\nCollecting Opinion article links...\n")
    links = get_opinion_links(5)

    for l in links:
        print(l)

    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(
        timeout=TIMEOUT,
        connector=connector
    ) as session:

        async def sem_fetch(url):
            async with semaphore:
                return await fetch_article(session, url)

        print("\nFetching articles concurrently...\n")
        articles = await asyncio.gather(*(sem_fetch(u) for u in links))

        # ---------- PRINT SPANISH ----------
        for i, art in enumerate(articles, 1):
            print("\n" + "=" * 70)
            print(f"ARTICLE {i}")
            print("SPANISH TITLE:", art["title"])
            print("\nCONTENT PREVIEW:\n", art["content"][:600])

        # ---------- DOWNLOAD IMAGES ----------
        print("\nDownloading images...\n")
        tasks = []
        for i, art in enumerate(articles, 1):
            if art["image"]:
                tasks.append(
                    download_image(session, art["image"], f"cover_{i}.jpg")
                )
        await asyncio.gather(*tasks)

        # ---------- TRANSLATE ----------
        print("\nTranslating titles...\n")
        spanish_titles = [a["title"] for a in articles]
        english_titles = await translate_titles(session, spanish_titles)

        for s, e in zip(spanish_titles, english_titles):
            print("\nES:", s)
            print("EN:", e)

        # ---------- WORD ANALYSIS ----------
        print("\nRepeated words (>2 occurrences):\n")
        repeats = repeated_words(english_titles)
        for w, c in repeats.items():
            print(w, ":", c)


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    asyncio.run(main())
