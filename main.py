from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import time

options = Options()
options.set_preference("intl.accept_languages", "es-ES,es")
# options.add_argument("--headless")  # IMPORTANT on many Linux systems

driver = webdriver.Firefox(options=options)

driver.get("https://elpais.com/")
time.sleep(5)

print(driver.title)
print(len(driver.page_source))

driver.quit()

