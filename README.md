# El País Opinion Scraper

A cross-browser scraper that extracts opinion articles from [El País](https://elpais.com/opinion/),
translates their titles to English, and runs in parallel across 5 browsers via BrowserStack Automate.

---

## Features

- Scrapes the first 5 articles from the El País Opinion section
- Prints each article's title and body content in Spanish
- Downloads and saves cover images as JPEG (with `og:image` fallback for columnist cards)
- Translates article titles from Spanish to English via the Rapid Translate Multi Traduction API
- Analyses translated titles for repeated words (stop-word filtered)
- Runs 5 parallel BrowserStack sessions across desktop and mobile browsers
- Persists raw results, clean output, and failed session logs as JSON

---

## Browser Matrix

| Session | Browser | OS / Device |
|---------|---------|-------------|
| 0 | Chrome (latest) | Windows 11 |
| 1 | Firefox (latest) | Windows 11 |
| 2 | Edge (latest) | Windows 11 |
| 3 | Safari 17 | macOS Sonoma |
| 4 | Chrome (latest) | iPhone 15 (real device) |

---

## Prerequisites

- Python 3.10 or higher (uses `str | None` union type syntax)
- A [BrowserStack Automate](https://www.browserstack.com/automate) account
- A [RapidAPI](https://rapidapi.com/) account with the
  [Rapid Translate Multi Traduction](https://rapidapi.com/sibaridev/api/rapid-translate-multi-traduction)
  API subscribed

---

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/Dacosmicgiant/browserstack_scrapper.git
cd browserstack_scrapper
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set environment variables

The scraper reads credentials from environment variables. Never hard-code them in the source.

**macOS / Linux (current session)**
```bash
export BROWSERSTACK_USERNAME="your_browserstack_username"
export BROWSERSTACK_ACCESS_KEY="your_browserstack_access_key"
export RAPIDAPI_KEY="your_rapidapi_key"
```

**macOS / Linux (permanent — add to `~/.bashrc` or `~/.zshrc`)**
```bash
echo 'export BROWSERSTACK_USERNAME="your_browserstack_username"' >> ~/.zshrc
echo 'export BROWSERSTACK_ACCESS_KEY="your_browserstack_access_key"' >> ~/.zshrc
echo 'export RAPIDAPI_KEY="your_rapidapi_key"' >> ~/.zshrc
source ~/.zshrc
```

**Windows (PowerShell)**
```powershell
$env:BROWSERSTACK_USERNAME="your_browserstack_username"
$env:BROWSERSTACK_ACCESS_KEY="your_browserstack_access_key"
$env:RAPIDAPI_KEY="your_rapidapi_key"
```

You can find your BrowserStack credentials at:
`https://automate.browserstack.com/dashboard` → **Access Key**

---

## Running the Scraper
Using browser stack
```bash
python elpais_opinion_browserstack.py
```
Using localhost
```bash
python elpais_opinion_local.py
```

Expected runtime is **5–6 minutes** due to 5 parallel sessions each fetching 5 full article pages.

---

## Output

All output is written to the `output/` and `images/` directories, which are created automatically.
```
project/
├── images/
│   ├── article_00_Caiga_quien_caiga.jpg
│   ├── article_01_Negar_un_techo_por_el_color_de_piel.jpg
│   ├── article_02_La_clase_media_no_es_un_invento_facha.jpg
│   ├── article_03_Fronteras__inteligentes___democracias_ne.jpg
│   └── article_04__Moteras_iranies_.jpg
├── output/
│   ├── results_raw.json       ← raw output from all 5 sessions
│   ├── output.json            ← deduplicated articles, translations, word freq
│   └── failed_sessions.json   ← any sessions with status "failed" or "no_data"
├── elpais_scraper.py
├── requirements.txt
└── README.md
```

### `output.json` structure
```json
{
  "timestamp": "2026-02-20T02:06:49",
  "articles": [
    {
      "index": 0,
      "title": "Caiga quien caiga",
      "title_en": "Whoever falls falls",
      "preview": "...",
      "content": "...",
      "image_url": "https://...",
      "image_path": "images/article_00_Caiga_quien_caiga.jpg",
      "article_url": "https://elpais.com/..."
    }
  ],
  "translations": [
    { "es": "Caiga quien caiga", "en": "Whoever falls falls" }
  ],
  "word_freq": {},
  "session_summary": {
    "success": 5,
    "no_data": 0,
    "failed": 0
  }
}
```

---

## Configuration

Key constants at the top of `elpais_scraper.py` can be adjusted without touching any logic:

| Constant | Default | Description |
|----------|---------|-------------|
| `ARTICLE_LIMIT` | `5` | Number of articles to scrape |
| `PARALLEL_RUNS` | `5` | Number of concurrent BrowserStack sessions |
| `SCROLL_ROUNDS` | `8` | Scroll iterations to trigger lazy-loaded content |
| `SCROLL_PAUSE` | `1.2` | Seconds to wait between each scroll step |
| `BUILD_NAME` | `"ElPais Opinion Scraper v3"` | Label shown in BrowserStack dashboard |

---

## How It Works

### 1. Language verification
After opening the homepage, the scraper reads the `<html lang="...">` attribute and
overrides `navigator.language` to `es-ES` to guard against geo-based redirects.

### 2. Article extraction
Navigates directly to `/opinion/`, dismisses the Didomi cookie banner, scrolls the
page to trigger lazy-loaded content, then tries a prioritised list of CSS selectors
to locate `<article>` elements. Falls back to any `<article>` on the page if the
specific selectors do not match (El País periodically restructures its DOM).

### 3. Image retrieval
Checks `<picture><source srcset>`, then `data-src` / `srcset` / `src` on `<img>`
elements. For columnist cards that have no listing image, falls back to the article
page's `og:image` meta tag, which El País sets on every article.

### 4. Translation
Sends all titles in a single batched POST to the Rapid Translate Multi Traduction API.
Handles both `list[str]` and `list[list[str]]` response shapes and pads missing
translations with the original Spanish text.

### 5. Word frequency
Tokenises translated titles with a regex that handles accented characters, filters
English stop-words, and reports words appearing more than twice. With only 5 diverse
headlines this threshold is typically not met, which is expected behaviour.

### 6. Parallel execution
Uses `asyncio.gather` over a `ThreadPoolExecutor` (Selenium's blocking I/O requires
threads). Each session runs independently; results are deduplicated by title before
the analysis phase.

---

## Troubleshooting

**`EnvironmentError: Missing environment variables`**
Ensure all three variables are exported in the same shell session you run the script from.

**`[extract] Fallback: found N <article> elements`**
The preferred CSS selectors did not match. The scraper still works via fallback.
El País occasionally changes its `data-dtm-region` attribute values — update
`OPINION_ARTICLE_SELECTORS` in the script if this persists across runs.

**Session status `no_data`**
Appears when a browser session connected successfully but extracted zero articles.
Check `failed_sessions.json` for details. Usually caused by a mobile layout
rendering the opinion section below the scroll threshold — increase `SCROLL_ROUNDS`.

**Images not saving**
Verify the `images/` directory is writable. If `og:image` fallback also fails, the
article may be behind a hard subscription wall that blocks all media.

**BrowserStack session timeout**
The default BrowserStack session timeout is 5 minutes. If your network is slow,
reduce `SCROLL_ROUNDS` or `SCROLL_PAUSE` to cut session time.

---

## License

MIT