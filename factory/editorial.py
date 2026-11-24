"""Technical validity and conservative editorial suitability are separate."""
import hashlib
import re
from difflib import SequenceMatcher
from .metadata import normalized


def _speech_intervals(transcript,candidates):
    intervals=[];selected=[]
    for segment in transcript.get('segments',[]):
        for c in candidates:
            a,b=c['start_seconds'],c['end_seconds']
            if segment['end']<=a or segment['start']>=b:continue
            selected_words=[w for w in segment.get('words',[]) if w['end']>a and w['start']<b]
            selected.append({**segment,'text':''.join(w['word'] for w in selected_words).strip() if selected_words else segment['text']})
            for unit in segment.get('words') or [segment]:
                lo,hi=max(a,unit['start']),min(b,unit['end'])
                if hi>lo:intervals.append((lo,hi))
    intervals.sort();merged=[]
    for a,b in intervals:
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged,selected


def assess(output,transcript,candidates,request,metadata,previous=(),preferences=None):
    preferences=preferences or {};technical=[];issues=[]
    if request.subtitle_language:issues.append('translated_subtitles_require_review')
    if output.get('hook_candidates'):issues.append('generated_hook_requires_review')
    validation=output.get('validation',{})
    if not validation.get('validated'):technical.append('output_not_technically_validated')
    if request.audio_mode=='silent' and validation.get('audio'):technical.append('silent_mode_has_audio')
    if request.audio_mode in ('original','music','voiceover') and transcript.get('segments') and not validation.get('audio'):technical.append('expected_audio_missing')
    if validation.get('audio_clipped_fraction',0)>.001:technical.append('decoded_audio_clipping')
    if validation.get('black_frame_fraction',0)>.9:issues.append('mostly_black_frames_require_review')
    if request.audio_mode not in ('silent','music') and validation.get('audio_silence_fraction',0)>preferences.get('max_silence_fraction',.65):issues.append('excessive_decoded_audio_silence')
    intervals,segments=_speech_intervals(transcript,candidates)
    text=' '.join(s['text'] for s in segments);digest=hashlib.sha256(normalized(text).encode()).hexdigest() if text else None
    duration=sum(c['end_seconds']-c['start_seconds'] for c in candidates)
    silence=max(0,1-sum(b-a for a,b in intervals)/duration) if intervals and duration else None
    if silence is not None and silence>preferences.get('max_silence_fraction',.65):issues.append('excessive_transcript_silence')
    for c in candidates:
        if c.get('editorial_review_required') or c.get('selection_method')=='heuristic':issues.append('heuristic_or_ungrounded_highlight')
        if c.get('score',100)<50:issues.append('weak_uncalibrated_highlight_score')
        for segment in segments:
            for word in segment.get('words',[]):
                if word['start']+.08<c['start_seconds']<word['end']-.08 or word['start']+.08<c['end_seconds']<word['end']-.08:issues.append('word_crosses_clip_boundary')
    if segments:
        if not re.search(r'[.!?…。！？][\s"”»)]*$',segments[-1]['text']):issues.append('natural_conclusion_unconfirmed')
        if re.match(r'^(and|but|because|however|але|і|тому|но|потому|y|pero)\b',segments[0]['text'].strip(),re.I):issues.append('opening_context_requires_review')
    elif request.audio_mode!='silent':issues.append('spoken_context_unavailable')
    if metadata.get('review_required') or metadata.get('validation_issues'):issues.append('metadata_requires_editorial_review')
    if request.source_attribution and request.source_attribution not in metadata.get('description',''):technical.append('required_attribution_missing')
    canonical=normalized(text)
    duplicate=bool(digest and any(p.get('transcript_sha256')==digest or (len(canonical)>=40 and p.get('comparison_text') and SequenceMatcher(None,canonical,p['comparison_text'],autojunk=False).ratio()>=.92) for p in previous))
    if duplicate:issues.append('duplicate_clip_transcript')
    state='REJECTED' if technical or duplicate else 'NEEDS_REVIEW' if issues else 'READY_FOR_REVIEW'
    return {'status':state,'technical_valid':not technical,'technical_issues':sorted(set(technical)),'issues':sorted(set(issues)),'review_required':state!='READY_FOR_REVIEW' or preferences.get('review_first',True),'transcript_sha256':digest,'comparison_text':canonical[:6000],'silence_fraction_estimate':silence,'silence_measurement':'word/segment coverage, not waveform VAD','human_reviewed':False,'scores_are_uncalibrated':True}
