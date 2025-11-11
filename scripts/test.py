import requests

headers = {
    "accept": "application/json",
    "Authorization": "Bearer YOUR_API_KEY"
}

response = requests.get('https://api.runpod.ai/v2/icdc5n1n38q0ke/health', headers=headers)