import requests, os
from config import TWELVE_DATA_API_KEY
url = f"https://api.twelvedata.com/economic_calendar?apikey={TWELVE_DATA_API_KEY}"
print(url[:50] + "...")
resp = requests.get(url)
print(resp.json())
