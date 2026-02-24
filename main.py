from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time

# configure language
chrome_options = Options()
chrome_options.add_argument("--lang=es-ES") # to make sure language stays Spanish
chrome_options.add_experimental_option(
    "prefs", {"intl.accept_languages": "es-ES"}
)

# Start the web driver
driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
    )

# open website
url="https://elpais.com/"
driver.get(url)

time.sleep(5) # wait for the page to load

print("Title: ", driver.title)
print("URL: ", driver.current_url)

html= driver.page_source
print("HTML length: ", len(html))

input("Press Enter to close the browser...")
driver.quit()