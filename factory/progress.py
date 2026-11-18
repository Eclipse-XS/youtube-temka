"""Measured stage checkpoints shared by local and remote workers."""
STAGES=[('source','Source Analysis'),('extraction','Download / Extraction'),('transcription','Transcription'),('language','Language Detection'),('highlights','AI Highlight Selection'),('retrieval','Video Retrieval'),('captions_audio','Audio / Caption Processing'),('rendering','Rendering'),('validation','Output Validation'),('drive','Google Drive Upload')]


class Progress:
    def __init__(self,update):
        self.update=update
        self.active=None
        self.counters={}

    def begin(self,key,state=None,total=None,unit=None,message=None):
        self.active=key
        s={'key':key,'status':'running','current':None,'total':total,'unit':unit,'message':message}
        self.counters[key]=s
        self.update(state,result={'active_stage':key},stage_update=s)

    def tick(self,current=None,total=None):
        if not self.active:
            self.update()
            return
        s=self.counters[self.active]
        if current is not None:s['current']=current
        if total is not None:s['total']=total
        self.update(current=s.get('current'),total=s.get('total'),stage_update=s)

    def done(self,key=None,status='completed',message=None):
        key=key or self.active
        if not key:return
        s={**self.counters.get(key,{'key':key}),'status':status,'message':message}
        if status=='completed' and s.get('total') is not None:s['current']=s['total']
        self.update(stage_update=s)
        if key==self.active:self.active=None
