import React from "react";

const styles = {
  pop:"Поява слова",karaoke:"Караоке",clean:"Чистий",gameplay_minimal:"Мінімальний ігровий",
  gaming_comic:"Ігровий комікс",bold_karaoke:"Виразне караоке",one_word:"Одне слово",
  two_to_three_words:"Коротка фраза",boxed_reaction:"На плашці",clean_longs:"Чистий для Longs",
  action_labels:"Мітки дій",
};

export default function CaptionTrackEditor({track,revision,duration,loadCues,onChange}) {
  const mode=track?.mode??"inherit";
  const appearance=track?.appearance||{};
  const changeStyle=(key,value)=>onChange({...track,appearance:{...appearance,[key]:value}});
  const changeCue=(index,fields)=>onChange({...track,cues:track.cues.map((cue,i)=>
    i===index?{...cue,...fields,words:[]}:cue)});
  const numeric=(key,label,min,max,step=1)=><label key={key}>{label}
    <input type="number" min={min} max={max} step={step} value={appearance[key]??""}
      onChange={e=>changeStyle(key,e.target.value===""?null:+e.target.value)}/>
  </label>;
  const color=(key,label)=><label key={key}>{label}
    <input type="text" pattern="#[0-9a-fA-F]{6}" placeholder="Колір стилю" value={appearance[key]??""}
      onChange={e=>changeStyle(key,e.target.value||null)}/>
  </label>;
  const select=(key,label,choices)=><label>{label}
    <select value={appearance[key]||""} onChange={e=>changeStyle(key,e.target.value||null)}>
      <option value="">Параметр стилю</option>
      {Object.entries(choices).map(([value,name])=><option key={value} value={value}>{name}</option>)}
    </select>
  </label>;
  return <details>
    <summary>Субтитри{revision?` · ревізія ${revision}`:""}</summary>
    <label>Режим
      <select value={mode} onChange={e=>{
        const next=e.target.value;
        onChange(next==="inherit"?null:{...track,mode:next,cues:next==="manual"?(track?.cues||[]):[]});
      }}>
        <option value="inherit">Як у завданні</option><option value="automatic">Автоматичні</option>
        <option value="manual">Ручні</option><option value="off">Вимкнені</option>
      </select>
    </label>
    {["automatic","manual"].includes(mode) && <div className="grid">
      <label>Стиль<select value={track.style||""} onChange={e=>onChange({...track,style:e.target.value||null})}>
        <option value="">Як у завданні</option>
        {Object.entries(styles).map(([value,label])=><option key={value} value={value}>{label}</option>)}
      </select></label>
      {select("font","Шрифт",{sans:"Без засічок",serif:"Із засічками",mono:"Моноширинний"})}
      {select("position","Позиція",{top:"Угорі",middle:"Посередині",bottom:"Унизу"})}
      {select("animation","Акцент слова",{none:"Колір",pop:"Масштаб",glow:"Сяйво",box:"Контур",highlight:"Плашка"})}
      {numeric("size","Розмір",12,48)}{numeric("words","Слів у групі",1,12)}
      {numeric("outline","Контур",0,8)}{numeric("shadow","Тінь",0,6)}
      {numeric("box_opacity","Непрозорість фону",0,1,.05)}
      {color("color","Колір тексту")}{color("active_color","Колір активного слова")}{color("box_color","Колір фону")}
    </div>}
    {mode==="manual" && <div>
      {!track.cues?.length && <button type="button" onClick={loadCues}>Завантажити розпізнаний текст</button>}
      {(track.cues||[]).map((cue,i)=><div className="grid" key={i}>
        <label>Початок, сек<input type="number" min="0" max={duration} step=".01" value={cue.start}
          onChange={e=>changeCue(i,{start:+e.target.value})}/></label>
        <label>Кінець, сек<input type="number" min=".01" max={duration} step=".01" value={cue.end}
          onChange={e=>changeCue(i,{end:+e.target.value})}/></label>
        <label>Текст<textarea maxLength="300" value={cue.text} onChange={e=>changeCue(i,{text:e.target.value})}/></label>
        <button type="button" onClick={()=>onChange({...track,cues:track.cues.filter((_,index)=>index!==i)})}>Прибрати рядок</button>
      </div>)}
      <button type="button" disabled={(track.cues?.at(-1)?.end??0)>=duration || (track.cues?.length??0)>=400}
        onClick={()=>{
          const start=track.cues?.at(-1)?.end??0;
          onChange({...track,cues:[...(track.cues||[]),{start,end:Math.min(start+1.5,duration),text:"",words:[]}]});
        }}>Додати рядок</button>
    </div>}
  </details>;
}
