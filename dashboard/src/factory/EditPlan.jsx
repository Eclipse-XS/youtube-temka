import React, { useState } from "react";

const soundKinds = {
  impact: "Удар",
  comedic_accent: "Комедійний акцент",
  whoosh: "Свист",
  bass_hit: "Басовий акцент",
  suspense: "Напружений акцент",
};

const effectKinds = {
  punch_in:"Наближення", animated_zoom:"Плавне наближення", crop:"Кадрування",
  freeze_frame:"Стоп-кадр", slow_motion:"Уповільнення", replay:"Повтор",
  text_overlay:"Текст поверх відео", image_overlay:"Зображення поверх відео",
  video_overlay:"Друге відео поверх кадру", visual_accent:"Кольорова рамка",
  gain:"Зміна гучності", audio_fade:"Плавна зміна гучності",
};

export default function EditPlan({ job, api, post, act, onSaved }) {
  const plan = job.result.edit_plan;
  const [segments,setSegments] = useState(plan.segments);
  const [target,setTarget] = useState(plan.target_duration);
  const [preview,setPreview] = useState(null);
  const [saving,setSaving] = useState(false);
  const [library,setLibrary] = useState(null);
  const path = "/jobs/"+job.id;
  const length = segments.reduce((sum,s)=>sum+s.end_seconds-s.start_seconds,0);
  const change = (id,key,value) => setSegments(items=>items.map(s=>s.id===id?{...s,[key]:value}:s));
  const changeSound = (segment,index,key,value) => change(segment.id,"sounds",
    segment.sounds.map((sound,i)=>i===index?{...sound,[key]:value}:sound));
  const changeEffect = (segment,index,fields) => change(segment.id,"effects",
    segment.effects.map((effect,i)=>i===index?{...effect,...fields}:effect));
  const save = (render) => act(async () => {
    setSaving(true);
    try {
      const body = {revision:plan.revision,target_duration:target,segments:segments.map(
        ({id,start_seconds,end_seconds,transition,transition_duration,hook,sounds,effects})=>
          ({id,start_seconds,end_seconds,transition,transition_duration,hook,sounds,effects}))};
      if (render) await post(path+"/render",body);
      else await api(path+"/edit-plan",{method:"PATCH",body:JSON.stringify(body)});
      await onSaved();
    } finally {
      setSaving(false);
    }
  });
  return <section>
    <h2>План монтажу</h2>
    <p>{length.toFixed(1)} сек · {segments.length} фрагментів</p>
    {target!==null && <label>Цільова тривалість, сек
      <input type="number" min="10" max="3600" value={target} onChange={e=>setTarget(+e.target.value)}/>
    </label>}
    {segments.map((s,index) => {
      const source = plan.sources[s.source_id];
      const start = s.start_seconds+s.source_offset, end = s.end_seconds+s.source_offset;
      const duration = end-start;
      const local = source.source.startsWith("upload:");
      let sourceLink;
      if (!local && source.source.startsWith("https://")) {
        const url = new URL(source.source);
        url.searchParams.set("t",Math.floor(start)+"s");
        sourceLink = url.toString();
      }
      return <article className="candidate" key={s.id}>
        <b>{s.title}</b>
        <p>{source.title} · {start.toFixed(1)}–{end.toFixed(1)} сек у джерелі</p>
        <small>{s.score==null?"":'Оцінка '+s.score.toFixed(1)+' · '}{s.reason}</small>
        <div className="grid">
          <label>Початок від початку аналізу, сек
            <input type="number" min="0" step=".1" value={s.start_seconds}
              onChange={e=>change(s.id,"start_seconds",+e.target.value)}/>
          </label>
          <label>Кінець від початку аналізу, сек
            <input type="number" min="0" step=".1" value={s.end_seconds}
              onChange={e=>change(s.id,"end_seconds",+e.target.value)}/>
          </label>
          <label>Перехід
            <select value={s.transition} onChange={e=>change(s.id,"transition",e.target.value)}>
              <option value="cut">Прямий монтаж</option><option value="fade">Затемнення</option>
              {job.request.mode==="longs" && index>0 && !job.request.silence_removal &&
                <option value="crossfade">Плавне накладання з попередньою сценою</option>}
            </select>
          </label>
          {s.transition!=="cut" && <label>Тривалість переходу, сек
            <input type="number" min=".1" max="2" step=".1" value={s.transition_duration??""}
              placeholder={s.transition==="crossfade"?"0.5":"0.25"}
              onChange={e=>change(s.id,"transition_duration",e.target.value===""?null:+e.target.value)}/>
          </label>}
        </div>
        <details>
          <summary>Напис і звукові ефекти</summary>
          <label><input type="checkbox" checked={s.hook!=null} onChange={e=>change(s.id,"hook",
            e.target.checked?{text:job.request.hook||"",start:0,end:null}:null)}/> Власний напис</label>
          {s.hook && <div className="grid">
            <label>Текст
              <input maxLength="120" value={s.hook.text} onChange={e=>change(s.id,"hook",{...s.hook,text:e.target.value})}/>
            </label>
            <label>Показати на секунді
              <input type="number" min="0" max={duration} step=".1" value={s.hook.start}
                onChange={e=>change(s.id,"hook",{...s.hook,start:+e.target.value})}/>
            </label>
            <label>Приховати на секунді
              <input type="number" min=".1" max={duration} step=".1" value={s.hook.end??""} placeholder="До кінця сцени"
                onChange={e=>change(s.id,"hook",{...s.hook,end:e.target.value===""?null:+e.target.value})}/>
            </label>
          </div>}
          {(s.sounds||[]).map((sound,i)=><div className="grid" key={i}>
            <label>Ефект
              <select value={sound.kind} onChange={e=>changeSound(s,i,"kind",e.target.value)}>
                {Object.entries(soundKinds).map(([kind,label])=><option key={kind} value={kind}>{label}</option>)}
              </select>
            </label>
            <label>Початок, сек
              <input type="number" min="0" max={duration} step=".1" value={sound.start}
                onChange={e=>changeSound(s,i,"start",+e.target.value)}/>
            </label>
            <label>Гучність
              <input type="number" min="0" max="1" step=".05" value={sound.gain}
                onChange={e=>changeSound(s,i,"gain",+e.target.value)}/>
            </label>
            <button type="button" onClick={()=>change(s.id,"sounds",s.sounds.filter((_,index)=>index!==i))}>Прибрати ефект</button>
          </div>)}
          <button type="button" disabled={s.sounds?.length>=8} onClick={()=>change(s.id,"sounds",
            [...(s.sounds||[]),{kind:"impact",start:0,gain:.25}])}>Додати звук</button>
        </details>
        {!job.request.silence_removal && <details onToggle={e=>{
          if (e.target.open && library===null) act(async()=>setLibrary(await api("/library")));
        }}>
          <summary>Ефекти монтажу</summary>
          {(s.effects||[]).map((effect,i)=>{
            const spatial=["punch_in","animated_zoom","crop"].includes(effect.kind);
            const overlay={image_overlay:"logos",video_overlay:"backgrounds"}[effect.kind];
            const numeric=(key,label,min,max,step,initial)=><label key={key}>{label}
              <input type="number" min={min} max={max} step={step} value={effect[key]??initial}
                onChange={e=>changeEffect(s,i,{[key]:+e.target.value})}/>
            </label>;
            return <div className="grid" key={effect.id||i}>
              <label>Тип ефекту
                <select value={effect.kind} onChange={e=>changeEffect(s,i,{kind:e.target.value,asset:null})}>
                  {Object.entries(effectKinds).map(([kind,label])=><option key={kind} value={kind}>{label}</option>)}
                </select>
              </label>
              {numeric("start","Початок, сек",0,duration,.1,0)}
              {numeric("end","Кінець, сек",.1,duration,.1,1)}
              {spatial && numeric("scale","Масштаб",1.01,3,.05,1.3)}
              {(spatial||overlay||effect.kind==="text_overlay") && <>
                {numeric("x","Горизонтальна позиція",0,1,.05,.5)}
                {numeric("y","Вертикальна позиція",0,1,.05,.5)}
              </>}
              {effect.kind==="slow_motion" && numeric("rate","Швидкість",.25,.95,.05,.5)}
              {effect.kind==="replay" && numeric("replay_start","Початок оригіналу, сек",0,effect.start,.1,0)}
              {effect.kind==="gain" && numeric("gain","Множник гучності",0,2,.05,.5)}
              {effect.kind==="audio_fade" && <label>Напрямок
                <select value={effect.fade_direction||"in"} onChange={e=>changeEffect(s,i,{fade_direction:e.target.value})}>
                  <option value="in">Наростання</option><option value="out">Затихання</option>
                </select>
              </label>}
              {effect.kind==="text_overlay" && <label>Текст
                <input maxLength="120" value={effect.text||""} onChange={e=>changeEffect(s,i,{text:e.target.value})}/>
              </label>}
              {["text_overlay","visual_accent"].includes(effect.kind) && <label>Колір
                <input type="color" value={effect.color||"#ffffff"} onChange={e=>changeEffect(s,i,{color:e.target.value})}/>
              </label>}
              {overlay && <label>Файл із бібліотеки
                <select value={effect.asset||""} onChange={e=>changeEffect(s,i,{asset:e.target.value||null})}>
                  <option value="">Виберіть файл</option>
                  {(library||[]).filter(item=>item.kind===overlay&&item.availability==="AVAILABLE").map(item=>
                    <option key={item.name} value={item.name}>{item.name}</option>)}
                </select>
              </label>}
              <button type="button" onClick={()=>change(s.id,"effects",s.effects.filter((_,index)=>index!==i))}>Прибрати ефект</button>
            </div>;
          })}
          <button type="button" disabled={s.effects?.length>=12} onClick={()=>change(s.id,"effects",
            [...(s.effects||[]),{kind:"punch_in",start:2,end:3,replay_start:0}])}>Додати ефект</button>
        </details>}
        <div className="actions">
          <button type="button" disabled={!index} onClick={()=>setSegments(items=>{
            const ordered=[...items];
            [ordered[index-1],ordered[index]]=[ordered[index],ordered[index-1]];
            if (ordered[0].transition==="crossfade") ordered[0]={...ordered[0],transition:"cut"};
            return ordered;
          })}>Вище</button>
          <button type="button" disabled={segments.length===1}
            onClick={()=>setSegments(items=>items.filter(item=>item.id!==s.id).map((item,i)=>
              i===0&&item.transition==="crossfade"?{...item,transition:"cut"}:item))}>Прибрати</button>
          {local && <button type="button" onClick={()=>setPreview(preview===s.id?null:s.id)}>Переглянути</button>}
          {sourceLink && <a href={sourceLink} target="_blank" rel="noreferrer">Відкрити джерело</a>}
        </div>
        {local && preview===s.id && <video controls preload="metadata"
          src={"/api/source-preview/"+encodeURIComponent(source.source.slice(7))+"#t="+Math.max(0,start)+","+end}/>}
      </article>;
    })}
    <div className="actions">
      <button type="button" disabled={saving} onClick={()=>save(false)}>Зберегти план</button>
      <button type="button" className="primary" disabled={saving} onClick={()=>save(true)}>Схвалити й рендерити</button>
    </div>
  </section>;
}
