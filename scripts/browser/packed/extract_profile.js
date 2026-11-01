await (async () => {
const LIMIT = 900;
const until = async ok => { for (let t = 0; t < 8000 && !ok(); t += 250) await new Promise(r => setTimeout(r, 250)); };
await until(() => document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img, input[type=password]') &&
document.querySelector('#lazyResumeHead'));
const clean = s => (s || '').replace(/[ \t\r\f\v]+/g, ' ').replace(/=/g, ':').replace(/\?\S*/g, '').trim();
const body = document.body ? document.body.innerText : '';
const overlays = [...document.querySelectorAll('[role=dialog], [role=alert], [class*=modal i], [class*=toast i], [class*=captcha i]')]
.filter(el => el.offsetParent).map(el => el.innerText).join(' ');
const focus = [document.title, overlays, body.length < 3000 ? body : ''].join(' ');
const challengeFrame = [...document.querySelectorAll('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .g-recaptcha')].some(el => {
if (el.closest('.grecaptcha-badge')) return false;
const r = el.getBoundingClientRect(), s = getComputedStyle(el);
return r.width > 10 && r.height > 10 && s.visibility !== 'hidden' && s.display !== 'none';
});
const signals = [];
if (/\/nlogin\//.test(location.pathname) || document.querySelector('input[type=password]')) signals.push('login_page');
else if (!document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img')) signals.push('logged_out');
if (challengeFrame || /captcha|are you a robot/i.test(focus)) signals.push('captcha');
if (/unusual (activity|traffic)|suspicious activity|automated (access|requests)|account (has been )?(restricted|suspended|blocked)/i.test(focus)) signals.push('unusual_activity');
if (/access denied|too many requests|forbidden|\b(403|429)\b/i.test(focus)) signals.push('blocked');
const hash = s => { let h = 5381; for (const c of s) h = (h * 33 + c.charCodeAt(0)) >>> 0; return h.toString(36); };
const sections = [...document.querySelectorAll('[id^=lazy]')].map(el => {
const lines = el.innerText.split(/\n+/).map(clean).filter(Boolean);
return { name: el.id.replace(/^lazy/, ''), text: lines.join(' | ') };
});
const updated = (body.match(/Profile last updated\s*-?\s*([^\n]+)/i) || [])[1] || '?';
const lines = [
`page: profile | signals: ${signals.join(',') || 'none'} | updated: ${clean(updated)}`,
'hashes: ' + sections.map(s => `${s.name} ${s.text ? hash(s.text) : '-'}`).join(', '),
...sections.map(s => `## ${s.name}: ${s.text || '(empty: scroll it into view)'}`)
];
const chunks = [];
let cur = '';
for (let l of lines) {
while (l.length > LIMIT) { if (cur) { chunks.push(cur); cur = ''; } chunks.push(l.slice(0, LIMIT)); l = l.slice(LIMIT); }
if (cur && cur.length + l.length + 1 > LIMIT) { chunks.push(cur); cur = ''; }
cur += (cur ? '\n' : '') + l;
}
if (cur) chunks.push(cur);
const k = Symbol.for('job-apply');
delete window[k];
Object.defineProperty(window, k, { value: { chunks: chunks.slice(1), i: 1, n: chunks.length }, configurable: true, writable: true });
return `[1/${chunks.length}]\n` + chunks[0];
})();
