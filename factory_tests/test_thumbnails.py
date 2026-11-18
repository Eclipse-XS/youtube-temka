import json
import hashlib
import httpx
from factory import config,store,youtube_thumbnails
from factory.thumbnails import create
from factory_tests.test_media import fixture


def test_thumbnail_uses_actual_decodable_frame_and_unicode_overlay(fixture):
    import cv2
    source,_,folder=fixture
    target=folder/'cover.jpg'
    report=create(source,target,'Природний голос · español')
    image=cv2.imread(str(target))
    assert image is not None and max(image.shape[:2])<=1280
    assert 0<report['selected_time']<6 and report['method']=='sampled_real_frames'
    assert report['text_applied']=='Природний голос · español'
    assert report['brightness']>0


def test_shorts_thumbnail_waits_processing_then_uses_same_video(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA',tmp_path);monkeypatch.setattr(config,'SCRATCH',tmp_path/'scratch');monkeypatch.setattr(config,'DB',tmp_path/'jobs.db')
    from factory import publisher
    monkeypatch.setattr(publisher,'token_file',lambda _:None)
    image=b'jpeg-fixture';uploads=[];processing=['processing']
    def handler(request):
        if request.url.path.endswith('/videos'):
            assert request.url.params['id']=='existing-video'
            return httpx.Response(200,json={'items':[{'snippet':{'channelId':'channel-fixture'},'processingDetails':{'processingStatus':processing[0]}}]})
        if request.url.path.endswith('/files/image-fixture'):return httpx.Response(200,content=image)
        assert request.url.path.endswith('/thumbnails/set')
        uploads.append(request)
        assert request.url.params['videoId']=='existing-video' and request.content==image
        return httpx.Response(200,json={'items':[{'default':{'url':'fixture'}}]})
    class Client:
        def __init__(self,*_):self.client=httpx.Client(transport=httpx.MockTransport(handler))
        def request(self,*args,**kwargs):return self.client.request(*args,**kwargs)
        def close(self):self.client.close()
    monkeypatch.setattr(youtube_thumbnails,'Drive',Client)
    publication={'id':'publication-fixture','alias':'fixture','video_id':'existing-video','channel':'channel-fixture','metadata':json.dumps({'format':'shorts','thumbnail':{'drive':{'id':'image-fixture','size':str(len(image)),'md5Checksum':hashlib.md5(image).hexdigest()}}})}
    youtube_thumbnails.apply(publication)
    with store.connect() as db:assert db.execute('SELECT state FROM publication_artifacts').fetchone()['state']=='WAITING_PROCESSING'
    assert not uploads
    processing[0]='succeeded';youtube_thumbnails.apply(publication)
    assert len(uploads)==1
    with store.connect() as db:assert db.execute('SELECT state FROM publication_artifacts').fetchone()['state']=='APPLIED'
