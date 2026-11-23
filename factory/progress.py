"""Measured stage checkpoints shared by local and remote workers."""
import time
from contextvars import ContextVar


MODEL_PROGRESS = ContextVar('factory_model_progress', default=None)

STAGES=[('source','Source Analysis'),('extraction','Download / Extraction'),('transcription','Transcription'),('language','Language Detection'),('highlights','AI Highlight Selection'),('hooks','Hook Candidates'),('retrieval','Video Retrieval'),('captions_audio','Audio / Caption Processing'),('rendering','Rendering'),('validation','Output Validation'),('metadata','Metadata Generation'),('editorial','Editorial Validation'),('drive','Drive Upload / Verification')]


class Progress:
    def __init__(self,update):
        self.update=update
        self.active=None
        self.counters={}
        self.source_id=None
        self.last_tick=0.0
        self.model_requests=0
        self.model_limits=None
        self.model_usage={}

    def begin(self,key,state=None,total=None,unit=None,message=None,*,operation=None,**details):
        self.active=key
        self.last_tick=time.monotonic()
        self.model_requests=0
        s={'key':key,'status':'running','current':None,'total':total,'unit':unit,'message':message,
           'source_id':self.source_id,'operation_id':operation or key,'details':details}
        self.counters[key]=s
        self.update(state,result={'active_stage':key},stage_update=s)

    def tick(self,current=None,total=None):
        if not self.active:
            self.update()
            return
        s=self.counters[self.active]
        if current is not None:s['current']=current
        if total is not None:s['total']=total
        now=time.monotonic()
        if now-self.last_tick<1:
            return
        self.update(current=s.get('current'),total=s.get('total'),stage_update=s)
        self.last_tick=now

    def done(self,key=None,status='completed',message=None,*,error_code=None):
        key=key or self.active
        if not key:return
        s={**self.counters.get(key,{'key':key,'source_id':self.source_id,'operation_id':key}),
           'status':status,'error_code':error_code}
        if message is not None:s['message']=message
        if status=='completed' and s.get('total') is not None:s['current']=s['total']
        self.update(stage_update=s)
        self.counters.pop(key,None)
        if key==self.active:self.active=None

    def next_model_request(self):
        self.model_requests+=1
        group=self.counters.get(self.active,{})
        return f"{group.get('operation_id','inference')}-model-{self.model_requests}"

    def limit_models(self,request,previous_usage):
        self.model_limits={'text':request.max_text_model_calls,'visual':request.max_visual_model_calls,
                           'context':request.max_model_context_tokens,'output':request.max_model_output_tokens,
                           'seconds':request.max_model_seconds}
        self.model_usage={key:previous_usage.get(key,0) for key in self.model_limits}

    def reserve_model(self,model_type,context,output):
        if self.model_limits is None:
            return float('inf')
        cost={model_type:1,'context':context,'output':output}
        remaining=self.model_limits['seconds']-self.model_usage['seconds']
        if remaining<=0 or any(self.model_usage[key]+value>self.model_limits[key] for key,value in cost.items()):
            return 0
        for key,value in cost.items():
            self.model_usage[key]+=value
        return remaining

    def model(self,operation,status,details,*,error_code=None):
        self.update(stage_update={'key':self.active or 'inference','source_id':self.source_id,
                                 'operation_id':operation,'status':status,'project':False,
                                 'error_code':error_code,'details':details})
