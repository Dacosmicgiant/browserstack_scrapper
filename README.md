# El País Opinion Scraper

A cross-browser Selenium scraper that visits the El País Spanish news outlet, scrapes articles from the Opinion section, translates their titles to English, and analyzes repeated words across the translated headers. Validated locally and executed across 5 parallel browser environments via BrowserStack.

---

## What It Does

1. Visits [elpais.com](https://elpais.com) and verifies the page is served in Spanish
2. Scrapes the first 5 articles from the Opinion section — title, content preview, and cover image
3. Translates the Spanish titles to English using the Rapid Translate Multi Traduction API
4. Identifies any words repeated more than twice across all translated titles
5. Runs across 5 parallel browser/device combinations on BrowserStack

---

## Requirements

- Python 3.8+
- A [BrowserStack Automate](https://automate.browserstack.com) account
- A [RapidAPI](https://rapidapi.com) key with access to the Rapid Translate Multi Traduction API

---

## Installation
```bash
git clone https://github.com/your-username/elpais-scraper.git
cd elpais-scraper
pip install -r requirements.txt
```

---

## Environment Variables

Set the following before running:
```bash
export BS_USER=your_browserstack_username
export BS_KEY=your_browserstack_access_key
export RAPID_API_KEY=your_rapidapi_key
```

On Windows:
```cmd
set BS_USER=your_browserstack_username
set BS_KEY=your_browserstack_access_key
set RAPID_API_KEY=your_rapidapi_key
```

---

## BrowserStack Configuration

Create a `browserstack.yml` file in the project root. Replace the credentials with your own:
```yaml
# =============================
# Set BrowserStack Credentials
# =============================
userName: your_browserstack_username
accessKey: your_browserstack_access_key

# ======================
# BrowserStack Reporting
# ======================
projectName: EL Pais Opinion Scraper
buildName: Selenium Multi Platform Run
buildIdentifier: '#${BUILD_NUMBER}'

# =======================================
# Platforms (5 parallel environments)
# =======================================
platforms:

  # -------- Desktop Browsers --------
  - os: OS X
    osVersion: Ventura
    browserName: Chrome
    browserVersion: latest
    chromeOptions:
      prefs:
        intl.accept_languages: "es-ES,es"

  - os: Windows
    osVersion: 11
    browserName: Edge
    browserVersion: latest
    edgeOptions:
      prefs:
        intl.accept_languages: "es-ES,es"

  - os: Windows
    osVersion: 10
    browserName: Firefox
    browserVersion: latest
    firefoxOptions:
      prefs:
        intl.accept_languages: "es-ES,es"

  # -------- Mobile Browsers --------
  - deviceName: Samsung Galaxy S22 Ultra
    osVersion: 12.0
    browserName: chrome
    realMobile: true
    chromeOptions:
      prefs:
        intl.accept_languages: "es-ES,es"

  - deviceName: iPhone 14
    osVersion: 16
    browserName: safari
    realMobile: true


# ==========================================
# BrowserStack Local (only if needed)
# ==========================================
browserstackLocal: false


# ===================
# Debugging features
# ===================
debug: false
networkLogs: false
consoleLogs: errors
```

> **Note:** Safari on iOS does not support language preference injection. El País defaults to Spanish regardless, so the Spanish language assertion in the test will still pass.

---

## Local Testing

To run locally with Firefox before pushing to BrowserStack, replace the fixture in `main.py` with:
```python
from selenium.webdriver.firefox.options import Options

@pytest.fixture()
def driver():
    options = Options()
    options.set_preference("intl.accept_languages", "es-ES,es")
    driver = webdriver.Firefox(options=options)
    yield driver
    driver.quit()
```

Then run:
```bash
pytest main.py -v
```

---

## BrowserStack Execution

Once validated locally, run across all 5 platforms in parallel:
```bash
browserstack-sdk pytest main.py -v
```

This will spin up sessions across:

| Platform                 | OS           | Browser |
|--------------------------|--------------|---------|
| Chrome latest            | OS X Ventura | Chrome  |
| Edge latest              | Windows 11   | Edge    |
| Firefox latest           | Windows 10   | Firefox |
| Samsung Galaxy S22 Ultra | Android 12.0 | Chrome  |
| iPhone 14                | iOS 16       | Safari  |

Results and session recordings are available on your [BrowserStack Automate dashboard](https://automate.browserstack.com).

---

## Project Structure
```
elpais-scraper/
├── main.py                 # scraper, pytest fixture, and test
├── browserstack.yml        # BrowserStack platform configuration
├── requirements.txt        
├── README.md               
└── images/                 # cover images saved here at runtime
```

---

## Notes

- Never commit real BrowserStack or RapidAPI credentials — use environment variables or a `.env` file and add it to `.gitignore`
- The `images/` directory is created automatically at runtime if it does not exist
- BrowserStack session name is set to `El Pais scraper` for easy identification in the dashboard