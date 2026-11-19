import React,{useState} from 'react';

export default function SelectionReview({job,post,act,onCreated}) {
  const sourceStart=job.request.start||0;
  const [mode,setMode]=useState(job.request.series_mode||'independent');
  const [count,setCount]=useState(job.request.count);
  const [minimum,setMinimum]=useState(job.request.minimum);
  const [maximum,setMaximum]=useState(Math.min(180,job.request.maximum));
  const [overlap,setOverlap]=useState(job.request.series_overlap??3);
  const rows=(job.result.candidates||[]).map((clip,id)=>({...clip,id,
    start:+(clip.start_seconds+sourceStart).toFixed(3),end:+(clip.end_seconds+sourceStart).toFixed(3)}));
  const [edited,setEdited]=useState(null);
  const parts=edited??rows;
  const available=['READY','FAILED','BLOCKED'].includes(job.state);
  const source=job.request.source;
  const update=(index,key,value)=>setEdited(parts.map((part,i)=>i===index?{...part,[key]:value}:part));
  const submit=(data)=>act(async()=>onCreated(await post('/jobs/'+job.id+'/replan',data)));
  const move=(index,direction)=>{
    const next=[...parts];
    [next[index],next[index+direction]]=[next[index+direction],next[index]];
    setEdited(next);
  };
  return <details open={job.request.plan_only||undefined}>
    <summary>План відбору Shorts</summary>
    {parts.map((part,index)=><article key={part.id}>
      <b>{part.part ? `Частина ${part.part}/${part.parts} · ` : ''}{part.title}</b>
      <p>{part.reason}</p>
      {[part.setup,part.development,part.payoff,part.connection].filter(Boolean).map((text,i)=><p key={i}>{text}</p>)}
      <p>{(part.end-part.start).toFixed(2)} с · {part.confidence>0?`оцінка моделі ${part.confidence}`:'потрібна перевірка'}{part.visual_review_required?' · перевірка відеоряду':''}</p>
      <div className="grid">
        <label>Початок, с<input type="number" min={sourceStart} step=".001" value={part.start} onChange={e=>update(index,'start',+e.target.value)}/></label>
        <label>Кінець, с<input type="number" step=".001" value={part.end} onChange={e=>update(index,'end',+e.target.value)}/></label>
      </div>
      {source.startsWith('upload:')&&<video controls preload="none" src={`/api/source-preview/${encodeURIComponent(source.slice(7))}#t=${part.start},${part.end}`}/>}
      {source.startsWith('https://www.youtube.com/watch?')&&<a target="_blank" rel="noreferrer" href={`${source}&t=${Math.floor(part.start)}s`}>Переглянути в джерелі</a>}
      <button type="button" disabled={!index} onClick={()=>move(index,-1)}>Вище</button>
      <button type="button" disabled={index===parts.length-1} onClick={()=>move(index,1)}>Нижче</button>
      <button type="button" onClick={()=>setEdited(parts.filter((_,i)=>i!==index))}>Відхилити</button>
      {job.result.planning_only&&!part.context_required&&part.payoff&&<button type="button" onClick={()=>submit({experiment:part.id})}>Рендерувати варіанти монтажу</button>}
    </article>)}
    {available&&<>
      <button type="button" onClick={()=>setEdited(null)}>Відновити план</button>
      <button type="button" disabled={parts.length>=20||(job.result.processing_end??sourceStart)<=sourceStart} onClick={()=>setEdited([...parts,{
        id:`manual-${Date.now()}`,title:'Власний інтервал',start:sourceStart,
        end:Math.min(sourceStart+45,job.result.processing_end)
      }])}>Додати власний інтервал</button>
      <button type="button" disabled={!parts.length||parts.some(p=>p.end<=p.start)} onClick={()=>submit({intervals:parts.map(p=>[p.start,p.end]),maximum})}>Підтвердити та рендерити</button>
      <div className="grid">
        <label>Режим<select value={mode} onChange={e=>setMode(e.target.value)}><option value="independent">Independent Highlights</option><option value="connected">Connected Story</option><option value="sequential">Sequential Source Split</option></select></label>
        <label>Кількість<input type="number" min="1" max="20" value={count} onChange={e=>setCount(+e.target.value)}/></label>
        <label>Мінімум, с<input type="number" min="5" max="180" value={minimum} onChange={e=>setMinimum(+e.target.value)}/></label>
        <label>Максимум, с<input type="number" min="5" max="180" value={maximum} onChange={e=>setMaximum(+e.target.value)}/></label>
        <label>Перекриття, с<input type="number" min="0" max="5" step=".1" value={overlap} onChange={e=>setOverlap(+e.target.value)}/></label>
      </div>
      <button type="button" onClick={()=>submit({mode,count,minimum,maximum,overlap})}>Перебудувати відбір</button>
    </>}
  </details>;
}
