import requests

#url=requests.get("https://content-sheets.googleapis.com/v4/spreadsheets/1a97kY35DXYIYocTge2wuHM3eVDRSbJZlwgxvuDePOVs/values/'Starcraft%20II'!A3%3AE?valueRenderOption=UNFORMATTED_VALUE&majorDimension=DIMENSION_UNSPECIFIED&dateTimeRenderOption=FORMATTED_STRING&key=AIzaSyCjE5SrCswLjWoHv1MKPxTB6RMkTPaIqzI")
#print(url)
#print(url.json())

import time
import json
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(ChromeDriverManager().install())
driver.get('https://cea.gg/pages/replay-vault')

time.sleep(5)

html = driver.execute_script("return document.getElementsByTagName('html')[0].innerHTML")
print(html)

# def process_browser_log_entry(entry):
#     response = json.loads(entry['message'])['message']
#     return response

# browser_log = driver.get_log('performance') 
# events = [process_browser_log_entry(entry) for entry in browser_log]
# events = [event for event in events if 'Network.response' in event['method']]
# WebDriverWait wait = new WebDriverWait(driver, SECONDS);

# asdf = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': events[0]["params"]["requestId"]})
# print(asdf)