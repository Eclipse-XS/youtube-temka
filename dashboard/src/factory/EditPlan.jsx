import React, { useState } from "react";

const soundKinds = {
  impact: "Удар",
  comedic_accent: "Комедійний акцент",
  whoosh: "Свист",
  bass_hit: "Басовий акцент",
};

export default function EditPlan({ job, api, post, act, onSaved }) {
  const plan = job.result.edit_plan;
  const [segments,setSegments] = useState(plan.segments);
  const [target,setTarget] = useState(plan.target_duration);
  const [preview,setPreview] = useState(null);
  const [saving,setSaving] = useState(false);
  const path = "/jobs/"+job.id;
  const length = segments.reduce((sum,s)=>sum+s.end_seconds-s.start_seconds,0);
  const change = (id,key,value) => setSegments(items=>items.map(s=>s.id===id?{...s,[key]:value}:s));
  const changeSound = (segment,index,key,value) => change(segment.id,"sounds",
    segment.sounds.map((sound,i)=>i===index?{...sound,[key]:value}:sound));
  const save = (render) => act(async () => {
    setSaving(true);
    try {
      const body = {revision:plan.revision,target_duration:target,segments:segments.map(
        ({id,start_seconds,end_seconds,transition,hook,sounds})=>({id,start_seconds,end_seconds,transition,hook,sounds}))};
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
            </select>
          </label>
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
        <div className="actions">
          <button type="button" disabled={!index} onClick={()=>setSegments(items=>{
            const ordered=[...items];
            [ordered[index-1],ordered[index]]=[ordered[index],ordered[index-1]];
            return ordered;
          })}>Вище</button>
          <button type="button" disabled={segments.length===1}
            onClick={()=>setSegments(items=>items.filter(item=>item.id!==s.id))}>Прибрати</button>
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
