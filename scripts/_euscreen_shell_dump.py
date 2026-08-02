import requests

url = "https://www.euscreen.eu/item.html?id=EUS_F665CD1BE6294477A3854352F04D6854"
r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 ShtetlFrames/1.0"})
print(r.text)
