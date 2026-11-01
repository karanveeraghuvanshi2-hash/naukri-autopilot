// Returns the next chunk stored by extract_cards.js, extract_jd.js or
// extract_profile.js, or '' when none are left. Pass this whole file as the
// `text` of javascript_tool.
(() => {
  const k = Symbol.for('job-apply');
  const s = window[k];
  if (!s || !s.chunks.length) return '';
  s.i += 1;
  const c = s.chunks.shift();
  if (!s.chunks.length) delete window[k];
  return `[${s.i}/${s.n}]\n` + c;
})()
