from typing import Literal
from pydantic import BaseModel, Field, model_validator


class JobRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2048)
    rights_confirmed: bool
    mode: Literal['shorts','longs'] = 'shorts'
    resolution: Literal[480,720,1080,'best'] = 720
    output_height: Literal[720,1080] = 720
    bitrate: int = Field(default=8000000,ge=1000000,le=50000000)
    caption_style: Literal['pop','karaoke','clean'] = 'pop'
    split_ratio: float = Field(default=.5,ge=.2,le=.8,allow_inf_nan=False)
    hook: str = Field(default='',max_length=120)
    preserve_fps: bool = False
    asr_model: Literal['tiny','base','small','medium','large-v3','large-v3-turbo'] | None = None
    llm_model: str | None = Field(default=None,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$')
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float = Field(default=1800, gt=0, le=86400, allow_inf_nan=False)
    count: int = Field(default=5, ge=1, le=20)
    minimum: float = Field(default=20, ge=5, le=600, allow_inf_nan=False)
    maximum: float = Field(default=60, ge=5, le=600, allow_inf_nan=False)
    preset: Literal['crop','blur','gameplay'] = 'blur'
    background: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]+\.mp4$')
    language: str | None = Field(default=None, pattern=r'^[a-z]{2,3}$')
    captions: bool = True
    save_drive: bool = True
    publish_channel: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,100}$')
    publish_automatic: bool = False
    intervals: list[tuple[float,float]] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def validate_job(self):
        if not self.rights_confirmed:
            raise ValueError('Confirm rights to the source and selected background')
        if self.publish_automatic and (not self.save_drive or not self.publish_channel):
            raise ValueError('Automatic publishing requires a selected authorized channel and verified Drive storage')
        if self.end <= self.start or self.minimum > self.maximum:
            raise ValueError('Invalid interval or clip duration bounds')
        if self.end-self.start > 3600:
            raise ValueError('This worker currently supports at most 60 minutes per job; choose a smaller interval')
        for a,b in self.intervals:
            import math
            if not math.isfinite(a+b) or not self.start <= a < b <= self.end:
                raise ValueError('Longs intervals must lie inside the processing interval')
        return self


class Candidate(BaseModel):
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    title: str = Field(min_length=1,max_length=150)
    language: str = Field(max_length=10)
    reason: str = Field(max_length=1000)
    confidence: float = Field(ge=0,le=1, allow_inf_nan=False)


class Ranking(BaseModel):
    candidates: list[Candidate] = Field(max_length=30)
