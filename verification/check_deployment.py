"""Read-only local health/auth smoke check; optional public model setup.

This script never prints credentials and never uploads a source file or video.
"""
import json
from pathlib import Path
import sys
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
token=dotenv_values(root/'.env').get('FACTORY_TOKEN','')
with httpx.Client(base_url='http://127.0.0.1:5175',timeout=15,trust_env=False) as client:
    assert client.get('/api/jobs').status_code==401
    client.headers['Authorization']='Bearer '+token
    settings=client.get('/api/settings')
    settings.raise_for_status()
    body=settings.json()
    result={'authenticated_settings':settings.status_code,'anonymous_jobs':401,'workers':len(body['workers']),'drive_configured':body['drive_configured'],'ollama_model':body['ollama_model']}
    if '--setup-model' in sys.argv:
        response=client.post('/api/settings/setup-model')
        response.raise_for_status()
        result['model_setup']=response.json()
    else:
        result['model_setup']=body.get('model_setup')
    (root/'verification'/'deployment.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
