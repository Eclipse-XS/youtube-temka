import json
from types import SimpleNamespace
import httpx
import pytest
from factory import metadata as m,config,store
from factory.models import JobRequest
from factory.editorial import assess


def context():
    return {'transcript':'The launch window opens tomorrow. Engineers completed the final checks.','source_title':'Launch briefing','source_url':'https://www.youtube.com/watch?v=fixture','intervals':[[20,45]],'highlight_explanations':[],'audio_language':'en','metadata_language':'en','content_category':'auto','duration':25,'mode':'shorts','source_attribution':'NASA, informational use; no endorsement','preferences':{}}


def draft():
    return m.PublishingMetadata(title='The launch window opens tomorrow',alternative_titles=['Engineers completed the final checks','The launch window'],description='Engineers completed the final checks.',tags=['launch','engineers'],hashtags=['#launch','#engineers'],category_id='28',audio_language='en',metadata_language='en',review_required=False)


def test_metadata_appends_credit_hashtags_and_keeps_three_titles():
    result=m.finalize(draft(),context())
    assert len(result.alternative_titles)==2 and result.category_id=='28'
    assert 'NASA, informational use; no endorsement' in result.description
    assert '#Shorts' in result.description and '#Shorts' in result.hashtags
    assert result.tags==['launch','engineers']


@pytest.mark.parametrize('field,value',[('title','Elon Musk cancels the launch'),('description','The rocket exploded yesterday.'),('tags',['bitcoin']),('hashtags',['#trending'])])
def test_unsupported_claims_fail_before_queue(field,value):
    proposal=draft().model_copy(update={field:value})
    with pytest.raises(ValueError):m.finalize(proposal,context())


def test_numbers_and_acronyms_are_not_invented_or_reinterpreted():
    ctx=context();ctx['transcript']='We are discussing LEO.'
    proposed=draft().model_copy(update={'title':'We are discussing Leo','alternative_titles':['We are discussing LEO','LEO'],'description':'We are discussing LEO.','tags':['LEO'],'hashtags':['#LEO','#Shorts']})
    with pytest.raises(ValueError,match='acronym'):m.finalize(proposed,ctx)


def test_tag_budget_counts_spaces_quotes_and_commas():
    tags=m.clean_tags(['two words']*5+['x'*80+str(i) for i in range(20)])
    assert len(tags)==len(set(tags)) and m.tag_cost(tags)<=500
    assert m.tag_cost(['two words','one'])==15


def test_multibyte_credit_is_never_lost_to_description_budget():
    ctx=context();ctx['source_attribution']='Автор: '+('ї'*990)
    result=m.fallback(ctx)
    assert len(result.description.encode())<=5000 and ctx['source_attribution'] in result.description
    assert result.review_required


def test_regenerate_once_then_fall_back_and_preserve_provenance():
    calls=[]
    def handler(request):
        payload=json.loads(request.content);calls.append(payload)
        return httpx.Response(200,json={'response':draft().model_copy(update={'title':'Invented billionaire event'}).model_dump_json()})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=m.Generator(client,{'layers':0,'used':False},'fixture-model').create(context())
    assert len(calls)==2 and 'validation_feedback' in json.loads(calls[-1]['prompt'])
    assert result['review_required'] and result['provenance']['method']=='extractive_fallback'
    assert result['_provenance']['input']['transcript']==context()['transcript']


def test_metadata_checkpoint_does_not_call_llm_again():
    ctx=context();old={'provenance':{'input_sha256':m.fingerprint(ctx)},'title':'Saved draft'}
    assert m.Generator(None,None,'model').create(ctx,old) is old


def test_metadata_translation_cannot_claim_dubbed_audio():
    ctx=context();ctx['metadata_language']='es'
    proposal=draft().model_copy(update={'title':'La ventana de lanzamiento','alternative_titles':['Ventana de lanzamiento','Comprobaciones finales'],'description':'La ventana de lanzamiento.','tags':['launch'],'hashtags':['#launch','#Shorts'],'audio_language':'es'})
    result=m.finalize(proposal,ctx)
    assert result.audio_language=='en' and result.metadata_language=='es' and result.review_required


def test_metadata_versions_keep_private_provenance_separate_from_polling(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path);monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch');monkeypatch.setattr(config,'DB',tmp_path/'jobs.db')
    job=store.create({'source':'fixture'});claim=store.claim('worker')
    value={**draft().model_dump(),'version':'v1','_provenance':{'input':context()}}
    store.update(job['id'],claim['lease'],state='READY',result={'outputs':[{'publishing_metadata':value,'approved':True,'editorial':{'technical_valid':True}}]})
    assert '_provenance' not in store.get(job['id'])['result']['outputs'][0]['publishing_metadata']
    assert store.metadata_history(job['id'],0)[0]['provenance']['input']['transcript']==context()['transcript']
    store.revise_metadata(job['id'],0,{**value,'version':'v2','title':'Manual revision'})
    assert len(store.metadata_history(job['id'],0))==2
    assert not store.get(job['id'])['result']['outputs'][0]['approved']


def test_editorial_quality_is_distinct_from_decodable_video():
    req=JobRequest(source='fixture',rights_confirmed=True)
    transcript={'segments':[{'start':0,'end':25,'text':'and then the unfinished thought','words':[]}]}
    result=assess({'validation':{'validated':True,'audio':True}},transcript,[{'start_seconds':0,'end_seconds':25,'selection_method':'heuristic'}],req,draft().model_dump())
    assert result['technical_valid'] and result['status']=='NEEDS_REVIEW'
    assert 'natural_conclusion_unconfirmed' in result['issues']


def test_near_duplicate_editorial_output_is_rejected_without_deleting_video():
    req=JobRequest(source='fixture',rights_confirmed=True)
    text='The launch window opens tomorrow. Engineers completed all the final checks.'
    output={'validation':{'validated':True,'audio':True}}
    candidates=[{'start_seconds':0,'end_seconds':25}]
    first=assess(output,{'segments':[{'start':0,'end':25,'text':text}]},candidates,req,draft().model_dump())
    second=assess(output,{'segments':[{'start':0,'end':25,'text':text.replace('all the','the')}]},candidates,req,draft().model_dump(),[first])
    assert second['status']=='REJECTED' and 'duplicate_clip_transcript' in second['issues']
    assert second['technical_valid'] is True
