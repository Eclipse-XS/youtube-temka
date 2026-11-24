"""Record the inputs, decisions and measurements needed to reproduce a render."""
from functools import lru_cache
from hashlib import file_digest
import os
from pathlib import Path
import subprocess

from ffmpeg_utils import video_encode_args
from . import config, media, stage_cache
from .assets import timeline_asset_files
from .render_timeline import fingerprint


@lru_cache(maxsize=1)
def application_commit():
    value = os.environ.get('FACTORY_BUILD_COMMIT')
    if value:
        return value
    try:
        return subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).resolve().parents[1],
                                       text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    except (OSError,subprocess.SubprocessError):
        return None


def checksum(path):
    if path is None or not path.is_file():
        return None
    identity = stage_cache.file_identity(path)
    shared = stage_cache.cache_path('sha256',[1,identity])
    digest = stage_cache.read_json(shared)
    if digest is None:
        with path.open('rb') as stream:
            digest = file_digest(stream,'sha256').hexdigest()
        if stage_cache.file_identity(path) != identity:
            raise ValueError('An input changed while its checksum was being recorded')
        stage_cache.save_json(shared,digest)
    return digest


def record(jid, timeline, sources, request, scenes, background, assets, hooks, outputs, progress, peaks):
    sources_used = {scene.candidate['source_id'] for scene in scenes}
    inputs = {}
    for identifier in sorted(sources_used):
        source = sources[identifier]
        local = media.local_source(source['source'])
        source_meta = source['metadata']
        inputs[identifier] = {'kind':source_meta.get('platform'),'duration':source_meta.get('duration'),
                              'video_id':source_meta.get('id'),'sha256':checksum(local)}
    files = {}
    for scene in scenes:
        files.update(timeline_asset_files(scene.request,background,scene.effects,assets))
    measurements = peaks.report()
    seconds = progress.stage_seconds.get('rendering',0)
    output_seconds = sum(output['duration'] for output in outputs)
    if seconds and not progress.cache_hits.get('scene_render'):
        measurements['output_seconds_per_render_second'] = round(output_seconds/seconds,3)
    encoder = video_encode_args()
    active_models = {request.llm_model or config.MODEL, request.visual_model}
    digests = {name:value for name,value in (progress.installed_models or {}).items()
               if name in active_models or name.removesuffix(':latest') in active_models}
    digests.update({item['model']:item['model_digest'] for item in progress.inference_metrics
                    if item.get('model') and item.get('model_digest')})
    return {'schema_version':1,'application_commit':application_commit(),'job_id':jid,
            'timeline_revision':timeline['revision'],'timeline_sha256':fingerprint(timeline),
            'sources':inputs,'source_ranges':timeline['segments'],
            'assets':{name:{'sha256':checksum(path)} for name,path in files.items()},
            'caption_tracks':[event for event in timeline['events'] if event['type']=='captions'],
            'hooks':hooks,'background_selection_seed':jid if request.background_mode=='random' else None,
            'models':{'asr':request.asr_model or config.ASR_MODEL,'text':request.llm_model or config.MODEL,
                      'visual':request.visual_model,'ollama_digests':digests},
            'encoder':{'arguments':encoder,'height':request.output_height,'bitrate':request.bitrate},
            'stage_seconds':{key:round(value,3) for key,value in progress.stage_seconds.items()},
            'inference':progress.inference_metrics,'inference_budget_usage':progress.model_usage,
            'resources':measurements,'cache_hits':progress.cache_hits,
            'outputs':[{'name':item['name'],'sha256':item['output_hash'],'validation':item['validation']} for item in outputs]}
