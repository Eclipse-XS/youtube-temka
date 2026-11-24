const styleFields = [
  "hook_font","hook_font_size","hook_color","hook_outline","hook_position","hook_x","hook_y",
  "hook_box","hook_box_opacity","hook_padding","hook_shadow","hook_wrap","hook_start","hook_duration",
  "hook_pinned","caption_style","caption_appearance","transition","audio_mode","music_asset",
  "editing_intensity","logo_asset","intro","outro","chapter_titles",
];

export function loadChannelStyle(channel) {
  try {
    const profile=JSON.parse(localStorage.getItem(`factory.channelStyle.${channel}`)||"{}");
    return Object.fromEntries(styleFields.filter(key=>key in profile).map(key=>[key,profile[key]]));
  } catch {
    return {};
  }
}

export function saveChannelStyle(channel,form) {
  const profile=Object.fromEntries(styleFields.filter(key=>form[key]!==undefined).map(key=>[key,form[key]]));
  localStorage.setItem(`factory.channelStyle.${channel}`,JSON.stringify(profile));
}
