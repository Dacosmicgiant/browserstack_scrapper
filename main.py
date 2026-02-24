# legacy code

# from selenium import webdriver
# from selenium.webdriver.firefox.options import Options
# import time

# options = Options()
# options.set_preference("intl.accept_languages", "es-ES,es")
# # options.add_argument("--headless")  # IMPORTANT on many Linux systems

# driver = webdriver.Firefox(options=options)

# driver.get("https://elpais.com/")
# time.sleep(5)

# print(driver.title)
# print(len(driver.page_source))

# driver.quit()

import os
import json
import requests
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

def extract_opinion_urls(soup):
    import json

    urls = []
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue

        try:
            data = json.loads(script.string)
        except:
            continue

        # recursive search
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

    return list(dict.fromkeys(urls))  # remove duplicates

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

# environment variables for headless mode and sandboxing
os.environ["MOZ_HEADLESS"] = "1"  # Run Firefox in headless mode
os.environ["MOZ_DISABLE_CONTENT_SANDBOX"] = "1"  # Disable content sandboxing

# configure Firefox options
options = Options()
options.set_preference("intl.accept_languages", "es-ES,es")
# options.add_argument("--headless")  # IMPORTANT on many Linux systems

driver = webdriver.Firefox(options=options)

# open EL PAIS
driver.get("https://elpais.com/")
time.sleep(5)

html = driver.page_source
soup = BeautifulSoup(html, "lxml")

article_urls = extract_opinion_urls(soup)[:5]

# legacy method

# scripts = soup.find_all("script", type="application/ld+json")
# print("JSON-LD scripts found:", len(scripts))
# for script in scripts:
#     try:
#         data = json.loads(script.string)
        
#         # sometimes  it's a list, sometimes dict
#         items = data if isinstance(data, list) else [data]

#         for item in items:
#             if "itemListElement" in item:
#                 for entry in item["itemListElement"]:
#                     url = entry.get("url", "")
#                     if "/opinion/" in url:
#                         article_urls.append(url)
#     except json.JSONDecodeError:
#         continue

# remove duplicates and keep first 5

article_urls = [
    u for u in extract_opinion_urls(soup)
    if "/opinion/" in u and not u.rstrip("/").endswith("/opinion")
][:5]

print("\n Found opinion articles:")
for url in article_urls:
    print(url)

os.makedirs("images", exist_ok=True)

spanish_titles = []
# Scrape each article
for i, url in enumerate(article_urls, 1):
    print("\n==============================")
    print("Scraping article", i)

    driver.get(url)
    time.sleep(4)

    article_soup = BeautifulSoup(driver.page_source, "lxml")

    # ---------------- TITLE ----------------
    title_tag = article_soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "No title"
    print("\nTITLE (Spanish):")
    print(title)
    spanish_titles.append(title)

    # ---------------- CONTENT ----------------
    paragraphs = article_soup.select("article p")
    content = "\n".join(p.get_text(strip=True) for p in paragraphs)

    print("\nCONTENT PREVIEW:")
    print(content[:500], "...")

    # ---------------- COVER IMAGE ----------------
    img = article_soup.find("figure")
    if img:
        img_tag = img.find("img")
        if img_tag and img_tag.get("src"):
            img_url = img_tag["src"]
            try:
                img_data = requests.get(img_url).content
                path = f"images/article_{i}.jpg"
                with open(path, "wb") as f:
                    f.write(img_data)
                print("Image saved:", path)
            except:
                print("Image download failed")
    else:
        print("No cover image found")
        
print("\n==============================")
print("TRANSLATING TITLES TO ENGLISH")

translated_titles = translate_titles_to_english(spanish_titles)

for es, en in zip(spanish_titles, translated_titles):
    print("\nSpanish:", es)
    print("English:", en)

driver.quit()
print("\nPART 2 COMPLETE")