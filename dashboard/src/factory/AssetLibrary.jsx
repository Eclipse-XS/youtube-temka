import React,{useEffect,useState} from 'react';
export default function AssetLibrary({api,post,act}) {
  const [items,setItems]=useState([]);
  const refresh=()=>api('/library').then(setItems);
  useEffect(()=>{refresh().catch(()=>{});},[]);
  return <section><h2>Додаткові відео та лого</h2><button onClick={()=>act(async()=>{await post('/library/bootstrap');await refresh();})}>Створити / перевірити шість оригінальних фонів</button>
    <label>Імпорт авторизованого MP4 / PNG<input type="file" accept=".mp4,.png" onChange={e=>{const file=e.target.files[0];if(!file)return;act(async()=>{if(!window.confirm('Ви маєте права на використання цього матеріалу?'))return;const body=new FormData();body.append('file',file);body.append('rights_confirmed','true');body.append(file.name.toLowerCase().endsWith('.png')?'logo':'background','true');await api('/uploads',{method:'POST',body});await refresh();});}}/></label>
    <p>Процедурні фони — CC0, 270×480, 24 FPS. Ігрові записи Minecraft/Subway Surfers додаються оператором із підтвердженими правами.</p>
    <div className="outputs">{items.map(item=><article key={item.id}><b>{item.name}</b><p>{item.category} · {item.width}×{item.height} · {item.duration.toFixed(1)} сек · {(item.size_bytes/1024**2).toFixed(1)} MB</p><details><summary>Прев’ю та походження</summary>{item.kind==='logos'?<img loading="lazy" src={`/api/library/${item.kind}/${item.name}`} alt={item.name}/>:<video controls preload="none" src={`/api/library/${item.kind}/${item.name}`}/>}<p>{item.source} · {item.license}</p></details></article>)}</div>
  </section>;
}
