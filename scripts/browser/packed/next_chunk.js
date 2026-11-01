(() => {
const k = Symbol.for('job-apply');
const s = window[k];
if (!s || !s.chunks.length) return '';
s.i += 1;
const c = s.chunks.shift();
if (!s.chunks.length) delete window[k];
return `[${s.i}/${s.n}]\n` + c;
})()
