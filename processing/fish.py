import requests

url = "http://services.dnr.state.mn.us/api/lakefinder/by_id/v1"

params = {
    "id": "FE5100DA-C25F-4425-9C5D-D1FF47CA3C10"
}

response = requests.get(url, params=params)

print(response.json())