"""Three sequential real local jobs with bounded RAM sampling; never publishes.

Uses the existing localhost controller and owned synthetic source fixture.
Drive persistence uses existing authorization; retention/public publishing stay off.
Raw samples and job IDs remain in ignored verification/runtime/.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import subprocess
import threading
import time
import zlib
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'verification'/'runtime'/('v7-long-source' if '--long-source' in sys.argv else 'v7-auto' if '--automatic-only' in sys.argv else 'v7')
RUNTIME.mkdir(parents=True,exist_ok=True)
TOKEN=dotenv_values(ROOT/'.env')['FACTORY_TOKEN']


def byte_value(value):
    number,unit=re.fullmatch(r'([\d.]+)\s*(\w+)',value.strip()).groups()
    return round(float(number)*{'B':1,'KiB':1024,'MiB':1024**2,'GiB':1024**3}[unit])


class Sampler:
    def __init__(self):self.stop=threading.Event();self.peaks={};self.samples=0;self.idle=[];self.errors=[]
    def measure(self):
        output=subprocess.check_output(['docker','stats','--no-stream','--format','{{.Name}}|{{.MemUsage}}',
                                        'youtube-temka-controller-1','youtube-temka-ollama-1','youtube-temka-web-1'],text=True,timeout=15)
        values={}
        for line in output.splitlines():
            name,usage=line.split('|');values[name]=byte_value(usage.split('/')[0])
        values['container_sum_bytes']=sum(values.values())
        try:values['system_gpu_used_mib']=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True,timeout=3).splitlines()[0])
        except (OSError,ValueError,subprocess.SubprocessError):pass
        return values
    def run(self):
        with (RUNTIME/'memory-samples.jsonl').open('w',encoding='utf-8') as output:
            while not self.stop.is_set():
                try:
                    values=self.measure();self.samples+=1
                    for key,value in values.items():self.peaks[key]=max(self.peaks.get(key,0),value)
                    output.write(json.dumps({'at':time.time(),**values})+'\n');output.flush()
                except Exception:self.errors.append('Sampler unavailable')
                self.stop.wait(1)


def logo_bytes():
    def chunk(kind,payload):return struct.pack('!I',len(payload))+kind+payload+struct.pack('!I',zlib.crc32(kind+payload)&0xffffffff)
    data=b''.join(b'\x00'+bytes([240,200,40,255])*64 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',64,64,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b'')


def main():
    sampler=Sampler();worker=threading.Thread(target=sampler.run,daemon=True)
    results=[];started=time.monotonic()
    with httpx.Client(base_url='http://127.0.0.1:5175',headers={'Authorization':'Bearer '+TOKEN},timeout=180,trust_env=False) as client:
        def get(path):
            response=client.get('/api'+path);response.raise_for_status();return response.json()
        def post(path,body=None):
            response=client.post('/api'+path,json=body or {});response.raise_for_status();return response.json()
        settings=get('/settings')
        assert not get('/storage/retention')['settings']['enabled'],'Memory verification never enables retention'
        assert not any(c['automatic'] for c in settings['channels']),'Disable automatic publishing before this controlled verification'
        library=get('/library');background=next(a['name'] for a in library if a['kind']=='backgrounds' and a['name'].startswith('starter-'))
        response=client.post('/api/uploads',files={'file':('v7-test-logo.png',logo_bytes(),'image/png')},data={'rights_confirmed':'true','logo':'true','license':'Original solid-color generated fixture'})
        response.raise_for_status();logo=response.json()['name']
        sampler.idle.append(sampler.measure());worker.start()
        cases=[
            {'name':'short_static_hook','mode':'shorts','preset':'crop','count':1,'minimum':5,'maximum':20,'intervals':[[0,20]],'text_mode':'hook_subtitles','hook':'A clear, friendly voice'},
            {'name':'connected_split_shorts','mode':'shorts','preset':'gameplay','background':background,'background_mode':'specific','count':3,'minimum':5,'maximum':10,'intervals':[[0,20]],'series_mode':'connected','series_overlap':3,'text_mode':'subtitles'},
            {'name':'long_timeline_logo_cta','mode':'longs','preset':'blur','count':2,'minimum':5,'maximum':20,'intervals':[[0,8],[12,20]],'text_mode':'subtitles','logo_asset':logo,'cta_text':'Subscribe for more videos.'},
        ]
        if '--automatic-only' in sys.argv:
            cases=[{'name':'automatic_grounded_short','mode':'shorts','preset':'crop','count':1,'minimum':5,'maximum':30,'end':None,'text_mode':'static_hook'}]
        if '--long-source' in sys.argv:
            cases=[{'name':'two_hour_source_chunks','mode':'shorts','preset':'crop','count':1,'minimum':5,'maximum':30,'end':None,'text_mode':'subtitles'}]
        try:
            for case in cases:
                name=case.pop('name')
                source_path=ROOT/'scratch'/'v7-fixtures'/'owned-2h.mp4' if '--long-source' in sys.argv else ROOT/'verification'/'source-en.mp4'
                with source_path.open('rb') as stream:
                    response=client.post('/api/uploads',files={'file':('owned-synthetic-source.mp4',stream,'video/mp4')},data={'rights_confirmed':'true'})
                response.raise_for_status();source=response.json()['source']
                request={'source':source,'rights_confirmed':True,'save_drive':bool(settings['drive_configured']),
                         'end':20,'language':'en','metadata_language':'en','source_attribution':'Owned synthetic speech and test pattern; controlled Factory verification',**case}
                task=post('/jobs',request);jid=task['id'];begin=time.monotonic();last=None;recovery_checked=False;reused=False;checkpoint_stamp=None;completed=0
                while time.monotonic()-begin<1800:
                    task=get('/jobs/'+jid)
                    if task['state']!=last:
                        print(name,task['state'],flush=True);last=task['state']
                    if '--long-source' in sys.argv and not recovery_checked and task['result'].get('audio_chunks_completed',0)>=2 and task['state']=='TRANSCRIBING':
                        completed=task['result']['audio_chunks_completed']
                        checkpoint_stamp=subprocess.check_output(['docker','exec','youtube-temka-controller-1','stat','-c','%Y:%s',f'/scratch/{jid}/transcript-0.json'],text=True).strip()
                        post('/jobs/'+jid+'/cancel')
                        post('/jobs/'+jid+'/retry')
                        recovery_checked=True
                        print(name,'CANCELLED_AND_REQUEUED',{'completed_checkpoints':completed},flush=True)
                        continue
                    if recovery_checked and not reused and task['result'].get('audio_chunks_completed',0)>completed:
                        after=subprocess.check_output(['docker','exec','youtube-temka-controller-1','stat','-c','%Y:%s',f'/scratch/{jid}/transcript-0.json'],text=True).strip()
                        assert after==checkpoint_stamp,'Retry rewrote a completed transcript checkpoint'
                        reused=True
                    if task['state'] in ('READY','FAILED','BLOCKED','CANCELLED'):break
                    time.sleep(2)
                (RUNTIME/(name+'.json')).write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf-8')
                assert task['state']=='READY',task.get('error') or task['state']
                outputs=task['result']['outputs']
                assert all(o['validation']['validated'] and o['output_hash'] for o in outputs)
                if name=='connected_split_shorts':
                    candidates=task['result']['candidates'];assert len(outputs)==3
                    assert all(abs(candidates[i]['end_seconds']-candidates[i+1]['start_seconds']-3)<.001 for i in range(2))
                if name=='long_timeline_logo_cta':
                    timeline=get('/jobs/'+jid+'/files/timeline.json');assert len(timeline['segments'])==2
                if name=='short_static_hook':
                    before=outputs[0]['output_hash']
                    post('/jobs/'+jid+'/outputs/0/approve',{'approved':True})
                    response=client.patch('/api/jobs/'+jid+'/outputs/0/metadata',json={'title':'A clear friendly voice'})
                    response.raise_for_status();revised=response.json()['result']['outputs'][0]
                    assert revised['output_hash']==before and not revised['approved']
                results.append({'case':name,'elapsed_seconds':round(time.monotonic()-begin,2),'outputs':len(outputs),
                                'durations':[o['duration'] for o in outputs],'cloud_verified':task['result'].get('cloud_verified',False),
                                'metadata_methods':[o['publishing_metadata']['provenance']['method'] for o in outputs],
                                'selection_method':task['result'].get('analysis'),
                                'audio_chunks_completed':task['result'].get('audio_chunks_completed'),
                                'real_cancel_retry':recovery_checked,
                                'checkpoint_reuse_verified':reused,
                                'actual_asr_stages':[s['status'] for s in task.get('stages',[]) if s['key']=='transcription']})
                time.sleep(3);sampler.idle.append(sampler.measure())
        finally:
            sampler.stop.set();worker.join(timeout=20)
            report={'results':results,'peaks':sampler.peaks,'idle_samples':sampler.idle,'sample_count':sampler.samples,
                    'sampling':'docker stats working set; one-second pause plus command runtime (typically about 2 seconds); system-wide GPU includes desktop overhead',
                    'elapsed_seconds':round(time.monotonic()-started,2),'sampler_errors':len(sampler.errors),
                    'limitations':['Sampling may miss short peaks; container sum excludes WSL VM cache/Windows and is not whole-host RAM','No public or private YouTube upload performed']}
            (RUNTIME/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report),flush=True)


if __name__=='__main__':main()
