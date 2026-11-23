import React,{useEffect,useState} from 'react';

export const layouts={auto:['Auto','Автоматичний вибір макета'],smart:['Fill Screen','Основне відео заповнює кадр'],crop:['Center Crop','Центральна частина кадру'],blur:['Blurred Sides','Основне відео на розмитому фоні'],gameplay:['Split Screen','Основне відео зверху, додаткове знизу']};
export const textModes={none:'No Text',subtitles:'Subtitles',static_hook:'Static Hook',hook_subtitles:'Hook + Subtitles',custom:'Custom Text'};
const captionStyles={pop:'Pop',karaoke:'Karaoke',clean:'Clean',gameplay_minimal:'Gameplay Minimal',
  gaming_comic:'Gaming Comic',bold_karaoke:'Bold Karaoke',one_word:'Одне слово',two_to_three_words:'До трьох слів',
  boxed_reaction:'Boxed Reaction',clean_longs:'Clean Longs',captions_off:'Вимкнені'};

export function LayoutPreview({form,thumbnail,video}) {
  const wide=form.mode==='longs',split=!wide&&form.preset==='gameplay',blur=!wide&&form.preset==='blur';
  const hookTop={top:12,center:45,bottom:65}[form.hook_position || 'top'];
  const frame=thumbnail ? <img src={thumbnail} alt="Кадр джерела"/> : video ? <video src={video} muted playsInline preload="metadata" controls/> : <span>Додайте джерело для перегляду кадру</span>;
  return <figure className="layout-preview"><div className={`layout-frame ${wide?'wide':''} ${blur?'blurred':''} ${split?'split':''}`}>
    <div className="main-frame" style={split?{height:`${(form.split_ratio||.5)*100}%`}:undefined}>{frame}</div>{split&&<div className="secondary-frame" style={{height:`${(1-(form.split_ratio||.5))*100}%`}}>{form.background_mode==='none'?'Додаткове відео вимкнене':form.background?<img src={`/api/library/backgrounds/${form.background}/frame`} alt="Кадр додаткового відео"/>:'Додаткове відео з бібліотеки'}</div>}
    {['static_hook','hook_subtitles','custom'].includes(form.text_mode)&&<strong className="preview-hook" style={{
      top:`${Math.max(5,Math.min(85,hookTop+100*(form.hook_y||0)/(wide ? form.output_height || 720 : 1920)))}%`,
      marginLeft:`${100*(form.hook_x||0)/(wide ? (form.output_height || 720)*16/9 : 1080)}%`,
      color:form.hook_color||'#fff',background:form.hook_box===false?'transparent':`rgba(0,0,0,${form.hook_box_opacity ?? .65})`,
      padding:`${(form.hook_padding ?? 14)/6}px`,whiteSpace:form.hook_wrap===false?'pre':'pre-wrap',
      fontFamily:{sans:'sans-serif',serif:'serif',mono:'monospace'}[form.hook_font||'sans'],fontSize:Math.max(9,(form.hook_font_size||48)/6)
    }}>{form.hook||'Заголовок відео'}</strong>}
    {(form.text_mode?['subtitles','hook_subtitles'].includes(form.text_mode):form.captions)&&<span className="preview-subtitles">Приклад субтитрів</span>}
    {form.logo_asset&&<span className="preview-logo"><img src={`/api/library/logos/${form.logo_asset}`} alt="Лого" style={{width:'100%'}}/></span>}
  </div><figcaption>Preview only · {layouts[form.preset]?.[1]}. Остаточне кадрування перевіряється після рендера.</figcaption></figure>;
}

export default function CompositionControls({form,set,backgrounds=[],channels=[],thumbnail,video}) {
  const [assets,setAssets]=useState([]);
  const captions=form.caption_appearance || {};
  const setCaption=(key,value)=>set('caption_appearance',{...captions,[key]:value});
  useEffect(()=>{fetch('/api/library').then(r=>r.ok?r.json():[]).then(setAssets).catch(()=>{});},[]);
  return <section className="composition-controls"><div className="grid">
    <label>Канал / профіль<select value={form.publish_channel||''} onChange={e=>{
      const channel=channels.find(c=>c.id===e.target.value);set('publish_channel',channel?.id||null);set('publish_automatic',false);
      if(channel?.preferences?.metadata_language)set('metadata_language',channel.preferences.metadata_language);
      if(channel?.preferences?.editing_preset)set('preset',channel.preferences.editing_preset);
    }}><option value="">Без публікації · ручний перегляд</option>{channels.map(c=><option key={c.id} value={c.id}>{c.preferences?.profile_name||c.title} · {c.preferences?.metadata_language||'auto'}</option>)}</select></label>
    <label>Текст<select value={form.text_mode||(form.captions?'subtitles':'none')} onChange={e=>{set('text_mode',e.target.value);set('captions',['subtitles','hook_subtitles'].includes(e.target.value));if(['none','subtitles'].includes(e.target.value))set('hook','');}}>{Object.entries(textModes).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
    {(form.captions || form.text_mode==='subtitles' || form.text_mode==='hook_subtitles' || form.caption_style==='captions_off') && <label>Стиль субтитрів
      <select value={form.caption_style || 'pop'} onChange={e=>set('caption_style',e.target.value)}>
        {Object.entries(captionStyles).map(([key,label])=><option key={key} value={key}>{label}</option>)}
      </select>
    </label>}
    {form.mode==='shorts'&&<label>Макет<select value={form.preset} onChange={e=>set('preset',e.target.value)}>{Object.entries(layouts).map(([id,[label]])=><option key={id} value={id}>{label}</option>)}</select></label>}
    {form.mode==='shorts'&&<label>Додаткове відео<select value={['none','random'].includes(form.background_mode)?form.background_mode:form.background||'auto'} onChange={e=>{set('background_mode',['none','auto','random'].includes(e.target.value)?e.target.value:'specific');set('background',['none','auto','random'].includes(e.target.value)?null:e.target.value);}}><option value="none">Без додаткового відео</option><option value="auto">Автовибір з бібліотеки</option><option value="random">Випадковий із категорії</option>{backgrounds.map(name=><option key={name}>{name}</option>)}</select></label>}
    {form.mode==='shorts'&&form.background_mode==='random'&&<label>Категорія фону<select value={form.background_category||''} onChange={e=>set('background_category',e.target.value||null)}><option value="">Усі дозволені</option>{[...new Set(assets.filter(a=>a.kind==='backgrounds').map(a=>a.category))].map(c=><option key={c}>{c}</option>)}</select></label>}
  </div>
  {['static_hook','hook_subtitles','custom'].includes(form.text_mode)&&<fieldset>
    <legend>Заголовок</legend>
    <div className="grid">
      <label>Текст<textarea maxLength={120} value={form.hook||''} placeholder="Залиште порожнім для AI-кандидатів" onChange={e=>set('hook',e.target.value)}/></label>
      <label>Початок, сек<input type="number" min="0" max="600" step=".1" value={form.hook_start ?? 0} onChange={e=>set('hook_start',+e.target.value)}/></label>
      <label>Тривалість, сек<input type="number" min=".5" max="30" step=".5" disabled={!!form.hook_pinned} value={form.hook_duration||3} onChange={e=>set('hook_duration',+e.target.value)}/></label>
      <label>Позиція<select value={form.hook_position||'top'} onChange={e=>set('hook_position',e.target.value)}><option value="top">Зверху</option><option value="center">По центру</option><option value="bottom">Знизу</option></select></label>
      <label>Зсув X, пікселі<input type="number" min="-480" max="480" value={form.hook_x ?? 0} onChange={e=>set('hook_x',+e.target.value)}/></label>
      <label>Зсув Y, пікселі<input type="number" min="-480" max="480" value={form.hook_y ?? 0} onChange={e=>set('hook_y',+e.target.value)}/></label>
      <label>Непрозорість підкладки<input type="number" min="0" max="1" step=".05" disabled={form.hook_box===false} value={form.hook_box_opacity ?? .65} onChange={e=>set('hook_box_opacity',+e.target.value)}/></label>
      <label>Внутрішній відступ, пікселі<input type="number" min="0" max="48" disabled={form.hook_box===false} value={form.hook_padding ?? 14} onChange={e=>set('hook_padding',+e.target.value)}/></label>
    </div>
    <label className="check"><input type="checkbox" checked={!!form.hook_pinned} onChange={e=>set('hook_pinned',e.target.checked)}/> Показувати до кінця кліпу</label>
    <label className="check"><input type="checkbox" checked={form.hook_wrap!==false} onChange={e=>set('hook_wrap',e.target.checked)}/> Автоматично переносити рядки</label>
  </fieldset>}
  {(form.captions || form.text_mode==='subtitles' || form.text_mode==='hook_subtitles') && form.caption_style!=='captions_off' && <details>
    <summary>Оформлення субтитрів</summary>
    <div className="grid">
      <label>Шрифт<select value={captions.font || ''} onChange={e=>setCaption('font',e.target.value || null)}>
        <option value="">Зі стилю</option><option value="sans">Sans</option><option value="serif">Serif</option><option value="mono">Mono</option>
      </select></label>
      <label>Позиція<select value={captions.position || ''} onChange={e=>setCaption('position',e.target.value || null)}>
        <option value="">Зі стилю</option><option value="top">Зверху</option><option value="middle">По центру</option><option value="bottom">Знизу</option>
      </select></label>
      {[
        ['size','Розмір',12,48,1], ['words','Слів у групі',1,12,1],
        ['duration','Максимальна тривалість групи, сек',.5,8,.1], ['outline','Обведення',0,8,1],
        ['box_opacity','Непрозорість підкладки',0,1,.05]
      ].map(([key,label,min,max,step])=><label key={key}>{label}
        <input type="number" min={min} max={max} step={step} value={captions[key] ?? ''} placeholder="Зі стилю"
          onChange={e=>setCaption(key,e.target.value===''?null:+e.target.value)} />
      </label>)}
      {[['color','Колір тексту','#ffffff'],['active_color','Колір поточного слова','#ffd700']].map(([key,label,fallback])=><label key={key}>{label}
        <input type="color" value={captions[key] || fallback} onChange={e=>setCaption(key,e.target.value)} />
      </label>)}
    </div>
    <button type="button" onClick={()=>set('caption_appearance',{})}>Відновити параметри стилю</button>
  </details>}
  <LayoutPreview form={form} thumbnail={thumbnail} video={video}/>
  <details><summary>Оформлення тексту та переклад</summary><div className="grid"><label>Шрифт<select value={form.hook_font||'sans'} onChange={e=>set('hook_font',e.target.value)}><option value="sans">Sans</option><option value="serif">Serif</option><option value="mono">Mono</option></select></label><label>Колір<input type="color" value={form.hook_color||'#ffffff'} onChange={e=>set('hook_color',e.target.value)}/></label><label>Розмір шрифту<input type="number" min="18" max="96" value={form.hook_font_size||48} onChange={e=>set('hook_font_size',+e.target.value)}/></label><label>Обведення<input type="number" min="0" max="8" value={form.hook_outline??2} onChange={e=>set('hook_outline',+e.target.value)}/></label><label>Переклад субтитрів<select value={form.subtitle_language||''} onChange={e=>set('subtitle_language',e.target.value||null)}><option value="">Мова оригіналу</option>{['en','es','pt-BR','de','ru','uk'].map(l=><option key={l}>{l}</option>)}</select></label></div>{[['hook_box','Підкладка'],['hook_shadow','Тінь']].map(([key,label])=><label className="check" key={key}><input type="checkbox" checked={form[key]??true} onChange={e=>set(key,e.target.checked)}/>{label}</label>)}<p>Переклад зберігає часові межі фраз і потребує редакторської перевірки.</p></details>
  </section>;
}
