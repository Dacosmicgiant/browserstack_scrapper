from collections import Counter
import re
import os
import json
import requests
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

# EXTRACT OPINION ARTICLE URLS FROM EL PAÍS HOMEPAGE

def extract_opinion_urls(soup):
    urls = []
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except:
            continue

        def find_urls(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "url" and isinstance(v, str) and "/opinion/" in v:
                        urls.append(v)
                    find_urls(v)

            elif isinstance(obj, list):
                for item in obj:
                    find_urls(item)

        find_urls(data)

    # remove duplicates
    return list(dict.fromkeys(urls))


# TRANSLATE TITLES

def translate_titles_to_english(spanish_titles):
    url = "https://rapid-translate-multi-traduction.p.rapidapi.com/t"

    payload = {
        "from": "es",
        "to": "en",
        "q": spanish_titles
    }

    headers = {
        "Content-Type": "application/json",
        "x-rapidapi-host": "rapid-translate-multi-traduction.p.rapidapi.com",
        "x-rapidapi-key": os.environ["RAPID_API_KEY"]
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    return response.json()

# FIND REPEATED WORDS

def find_repeated_words(titles, min_count=3):
    all_words = []

    for title in titles:
        title = title.lower()
        title = re.sub(r"[^\w\s]", "", title)
        all_words.extend(title.split())

    stopwords = {
        "the","a","an","of","to","in","on","for","and","or",
        "with","at","by","from","is","are","was","were"
    }

    filtered = [w for w in all_words if w not in stopwords]
    counts = Counter(filtered)

    return {w: c for w, c in counts.items() if c >= min_count}


# SCRAPE SINGLE ARTICLE

def scrape_single_article(driver, url, index, image_dir="images"):
    print("\n==============================")
    print("Scraping article", index)

    driver.get(url)
    time.sleep(4)

    soup = BeautifulSoup(driver.page_source, "lxml")

    # ----- TITLE -----
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "No title"

    print("\nTITLE (Spanish):")
    print(title)

    # ----- CONTENT -----
    paragraphs = soup.select("article p")
    content = "\n".join(p.get_text(strip=True) for p in paragraphs)

    print("\nCONTENT PREVIEW:")
    print(content[:500], "...")

    # ----- IMAGE -----
    os.makedirs(image_dir, exist_ok=True)

    img_url = None

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        img_url = og["content"]

    if not img_url:
        img = soup.select_one("article img")
        if img and img.get("src"):
            img_url = img["src"]

    if img_url:
        try:
            img_data = requests.get(img_url, timeout=10).content
            path = f"{image_dir}/article_{index}.jpg"
            with open(path, "wb") as f:
                f.write(img_data)
            print("Image saved:", path)
        except Exception as e:
            print("Image download failed:", e)
    else:
        print("No image found")

    return title


# SCRAPE MULTIPLE ARTICLES

def scrape_articles(driver, article_urls):
    spanish_titles = []

    for i, url in enumerate(article_urls, 1):
        title = scrape_single_article(driver, url, i)
        spanish_titles.append(title)

    return spanish_titles


# =========================================================
# MAIN EXECUTION
# =========================================================

# headless firefox
os.environ["MOZ_HEADLESS"] = "1"
os.environ["MOZ_DISABLE_CONTENT_SANDBOX"] = "1"

options = Options()
options.set_preference("intl.accept_languages", "es-ES,es")

driver = webdriver.Firefox(options=options)

# open homepage
driver.get("https://elpais.com/")
time.sleep(5)

soup = BeautifulSoup(driver.page_source, "lxml")

# extract and filter opinion URLs
all_urls = extract_opinion_urls(soup)

article_urls = [
    u for u in all_urls
    if "/opinion/" in u and not u.rstrip("/").endswith("/opinion")
][:5]

print("\nFound opinion articles:")
for url in article_urls:
    print(url)

# scrape
spanish_titles = scrape_articles(driver, article_urls)

driver.quit()

# TRANSLATION

print("\n==============================")
print("TRANSLATING TITLES TO ENGLISH")

translated_titles = translate_titles_to_english(spanish_titles)

for es, en in zip(spanish_titles, translated_titles):
    print("\nSpanish:", es)
    print("English:", en)

# WORD ANALYSIS
print("\n==============================")
print("REPEATED WORDS (count > 2)")

repeated_words = find_repeated_words(translated_titles, min_count=3)

if repeated_words:
    for word, count in repeated_words.items():
        print(word, "->", count)
else:
    print("No words repeated more than twice.")

print("\nPART 2 COMPLETE")