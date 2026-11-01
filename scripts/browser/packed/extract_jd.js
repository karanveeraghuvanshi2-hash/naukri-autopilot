await (async () => {
const LIMIT = 900;
const until = async ok => { for (let t = 0; t < 8000 && !ok(); t += 250) await new Promise(r => setTimeout(r, 250)); };
await until(() => document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img, input[type=password]') &&
document.querySelector('h1[class*=jd-header-title]'));
const clean = s => (s || '').replace(/[ \t\r\f\v]+/g, ' ').replace(/=/g, ':').trim();
const one = sel => clean(document.querySelector(sel)?.textContent).replace(/\n+/g, ' ');
const all = sel => [...document.querySelectorAll(sel)].map(e => clean(e.textContent).replace(/\n+/g, ' ')).filter(Boolean);
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
if (/daily quota (expired|exceeded)|quota expired/i.test(body)) signals.push('quota');
const id = (location.pathname.match(/-(\d+)$/) || [])[1] || '?';
const applyText = one('#apply-button');
let apply = 'none';
if (/^applied/i.test(applyText)) apply = 'applied';
else if (document.querySelector('#company-site-button')) apply = 'company_site';
else if (/^apply/i.test(applyText)) apply = 'naukri';
else if (/no longer (available|accepting)|job (has )?expired/i.test(body)) apply = 'closed';
else if ([...document.querySelectorAll('button, a')].some(b => /^(login|register) to apply/i.test(clean(b.textContent)))) apply = 'login';
const match = [...document.querySelectorAll('[class*=MS__details] i')]
.map(i => clean(i.parentElement.textContent).toLowerCase() + (/check_circle/.test(i.className) ? '+' : '-'));
const stats = all('[class*="jhc__stat__"]').join(' | ');
const rating = one('[class*=jhc__jd-top-head] [class*=amb-rating]');
const reviews = one('[class*=jhc__jd-top-head] [class*=amb-review]').replace(/\D/g, '');
const lines = [
`page: jd | id: ${id} | apply: ${apply} | signals: ${signals.join(',') || 'none'}`,
`title: ${one('h1[class*=jd-header-title]')}`,
`company: ${one('[class*=jd-header-comp-name] a') || one('[class*=jd-header-comp-name]')}` + (rating ? ` | rating: ${rating}` : '') + (reviews ? ` (${reviews} reviews)` : ''),
`exp: ${one('[class*="jhc__exp__"]')} | salary: ${one('[class*="jhc__salary__"]')} | mode: ${one('[class*="jhc__wfhmode__"]') || '?'} | location: ${one('[class*="jhc__location__"]')}`,
stats,
`naukri match: ${match.join(', ') || '?'}`,
all('[class*=other-details] [class*=details]').join(' ').slice(0, 400),
`education: ${all('[class*=education] [class*=details]').join(' ').slice(0, 200) || '?'}`,
`skills: ${all('[class*=key-skill] a').join(', ').slice(0, 400)}`
];
const desc = (document.querySelector('[class*=JDC__dang-inner-html]')?.innerText || '').replace(/=/g, ':');
lines.push(`description (${desc.length} chars):`);
const descLines = desc.split(/\n+/).map(clean).filter(Boolean);
const chunks = [];
let cur = '';
for (let l of [...lines, ...descLines]) {
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
