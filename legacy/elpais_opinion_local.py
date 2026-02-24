import os
import asyncio
import aiohttp
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


ELPAIS_URL = "https://elpais.com"

TRANSLATE_URL = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"

HEADERS = {
    "Content-Type": "application/json",
    "x-rapidapi-host": "rapid-translate-multi-traduction.p.rapidapi.com",
    "x-rapidapi-key": os.getenv("RAPIDAPI_KEY")
}


# -----------------------------
# Selenium scraper
# -----------------------------
def scrape_opinion_titles():
    print("Opening browser...")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        driver.get(ELPAIS_URL)

        print("Waiting for opinion section...")

        section = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "section[data-dtm-region='portada_tematicos_opinion']")
            )
        )

        articles = section.find_elements(By.CSS_SELECTOR, "h3 a")

        titles = []
        for a in articles:
            text = a.text.strip()
            if text:
                titles.append(text)

        print(f"Collected {len(titles)} titles")
        return titles

    finally:
        print("Closing browser...")
        driver.quit()


# -----------------------------
# Async translator (RapidAPI)
# -----------------------------
async def translate_titles(spanish_titles):
    if not spanish_titles:
        return []

    print("Translating titles (batch request)...")

    payload = {
        "from": "es",
        "to": "en",
        "q": spanish_titles
    }

    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            TRANSLATE_URL,
            headers=HEADERS,
            json=payload
        ) as r:
            r.raise_for_status()
            return await r.json()


# -----------------------------
# Word frequency helper
# -----------------------------
def word_frequency(titles):
    from collections import Counter
    import re

    words = []
    for title in titles:
        words.extend(re.findall(r"[a-zA-Z']+", title.lower()))

    return Counter(words)


# -----------------------------
# Main pipeline
# -----------------------------
async def main():
    spanish_titles = scrape_opinion_titles()

    if not spanish_titles:
        print("No titles found.")
        return

    english_titles = await translate_titles(spanish_titles)

    print("\n--- TRANSLATIONS ---")
    for es, en in zip(spanish_titles, english_titles):
        print(f"ES: {es}")
        print(f"EN: {en}\n")

    print("\n--- REPEATED WORDS (ENGLISH) ---")
    freq = word_frequency(english_titles)
    for word, count in freq.most_common(10):
        if count > 1:
            print(word, count)


# -----------------------------
# Entry point
# -----------------------------
if __name__ == "__main__":
    if not os.getenv("RAPIDAPI_KEY"):
        raise ValueError("RAPIDAPI_KEY not set in environment")

    asyncio.run(main())
