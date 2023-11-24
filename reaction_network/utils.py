import json

import requests

ASKCOS_URL = "http://72.70.38.130"


def query_askcos_condition_rec(reaction_smiles: str) -> dict:
    response = requests.post(
        headers={"Content-type": "application/json"},
        url=f"{ASKCOS_URL}:9918/api/context-recommender/v2/predict/FP/call-sync",
        data=f'{{"smiles": "{reaction_smiles}", "n_conditions": 3}}',
    )
    response = response.content.decode('utf8')
    response = json.loads(response)
    assert response['status_code'] == 200
    return response


def drawing_url(smiles: str, size=80) -> str:
    smiles = smiles.replace("+", "%2b")
    q = f"/api/draw/?smiles={smiles}&transparent=true&annotate=false&size={size}"
    q = ASKCOS_URL + q
    return q
