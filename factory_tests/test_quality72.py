from factory.metadata import Generator, context
from factory.models import JobRequest


def test_confirmed_gta_context_does_not_copy_transcript_or_source_claim():
    request=JobRequest(source='https://www.youtube.com/watch?v=fixture',rights_confirmed=True,
                       source_category='gameplay',confirmed_subject='GTA',
                       clip_observation='Driving and on-foot gameplay',metadata_language='en')
    ctx=context({'language':'en','segments':[{'start':0,'end':4,'text':'Park this, huh?'}]},
                request,{'title':'GTA 6 NEW FOOTAGE'},[{'start_seconds':0,'end_seconds':45}],
                {'duration':45},request.source)
    draft=Generator(None,None,None).create(ctx)
    assert draft['title']=='GTA | Driving and on-foot gameplay'
    assert draft['category_id']=='20'
    assert 'GTA 6' not in draft['description'] and request.source not in draft['description']
    assert draft['tags']==['GTA','GTA gameplay','gaming clips']
    assert draft['hashtags']==['#GTA','#Gaming','#Shorts']
    assert len(draft['title_candidates'])>=5 and draft['review_required']


def test_gameplay_override_and_attribution_are_respected():
    request=JobRequest(source='https://www.youtube.com/watch?v=fixture',rights_confirmed=True,
                       source_category='gameplay',category_override='26',source_attribution='Credit: Example',
                       attribution_required=True,include_source_link=True)
    ctx=context({'language':'en','segments':[]},request,{'title':'GTA 6'},
                [{'start_seconds':0,'end_seconds':45}],{'duration':45},request.source)
    draft=Generator(None,None,None).create(ctx)
    assert 'game_identity_unconfirmed' in draft['validation_issues']
    assert 'category_override_conflicts_with_gameplay' in draft['validation_issues']
    assert draft['category_id']=='26' and 'Credit: Example' in draft['description']
    assert request.source in draft['description']

def test_unverified_source_title_can_route_to_gaming_without_claiming_an_edition():
    request=JobRequest(source='https://www.youtube.com/watch?v=fixture',rights_confirmed=True)
    ctx=context({'language':'en','segments':[]},request,{'title':'GTA 6 alleged gameplay'},
                [{'start_seconds':0,'end_seconds':45}],{'duration':45},request.source)
    data=Generator(None,None,None).create(ctx)
    assert data['category_id']=='20' and 'GTA' not in data['title']
    assert 'game_identity_unconfirmed' in data['validation_issues']
