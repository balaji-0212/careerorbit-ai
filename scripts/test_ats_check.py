import requests

for s in ['atlan', 'hasura', 'yellowai', 'whatfix', 'hevodata', 'lambdatest', 'headout', 'postman']:
    try:
        r = requests.get(f'https://boards-api.greenhouse.io/v1/boards/{s}/jobs', timeout=3)
        if r.status_code == 200:
            print('GH:', s, 'count=', len(r.json().get('jobs', [])))
    except Exception:
        pass
    try:
        r2 = requests.get(f'https://api.lever.co/v0/postings/{s}?limit=5', timeout=3)
        if r2.status_code == 200 and isinstance(r2.json(), list):
            print('Lever:', s, 'count=', len(r2.json()))
    except Exception:
        pass
