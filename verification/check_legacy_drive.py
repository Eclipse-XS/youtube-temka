"""Read-only validation of the discovered original Drive OAuth pair."""
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=Path(os.environ['LOCALAPPDATA'])/'AIContentFactory'/'drive'
client=root/'client.json'
token=root/'token.json'
before=[hashlib.sha256(p.read_bytes()).digest() for p in (client,token)]
os.environ['DRIVE_OAUTH_CLIENT_FILE']=str(client)
os.environ['DRIVE_OAUTH_TOKEN_FILE']=str(token)
from factory.drive import Drive,BASE
result={'legacy_files_present':True,'authorized':False,'files_unchanged':False}
drive=None
try:
    drive=Drive()
    response=drive.request('GET',BASE+'/about',params={'fields':'storageQuota'})
    result['authorized']=response.status_code==200
except Exception:
    result['error']='Existing authorization could not be verified; no token contents were displayed or modified.'
finally:
    if drive:
        drive.close()
    result['files_unchanged']=before==[hashlib.sha256(p.read_bytes()).digest() for p in (client,token)]
    Path(__file__).with_name('oauth-status.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
