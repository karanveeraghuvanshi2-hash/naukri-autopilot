await (async () => {
const LIMIT = 900;
const RULES = { seen: '', exclude: '' };
const until = async ok => { for (let t = 0; t < 8000 && !ok(); t += 250) await new Promise(r => setTimeout(r, 250)); };
await until(() => document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img, input[type=password]') &&
document.querySelector('div.srp-jobtuple-wrapper[data-job-id], article.jobTuple[data-job-id]'));
const clean = s => (s || '').replace(/\s+/g, ' ').replace(/[|=]/g, '/').trim();
const txt = (root, sel) => clean(root.querySelector(sel)?.textContent);
const num = s => (s.match(/\d+(\.\d+)?/) || [''])[0];
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
const row = (id, href, f) => {
const path = href ? new URL(href, location.origin).pathname : '';
const m = path.match(/^\/job-listings-(.+)-(\d+)$/);
const slug = m && m[2] === id ? m[1] : path;
return [id, f.title.slice(0, 80), f.company.slice(0, 50), f.exp, f.salary, f.location.slice(0, 80),
f.posted, num(f.rating), num(f.reviews), f.tags.slice(0, 100), slug].join('|');
};
let page = 'unknown';
let rows = [];
const srp = document.querySelectorAll('div.srp-jobtuple-wrapper[data-job-id]');
const rec = document.querySelectorAll('article.jobTuple[data-job-id]');
if (srp.length) {
page = 'search';
rows = [...srp].map(w => row(w.dataset.jobId, w.querySelector('a.title')?.getAttribute('href'), {
title: txt(w, 'a.title'), company: txt(w, 'a.comp-name'), rating: txt(w, '.rating'), reviews: txt(w, '.review'),
exp: txt(w, '.expwdth'), salary: txt(w, '.sal-wrap'), location: txt(w, '.locWdth'), posted: txt(w, '.job-post-day'),
tags: [...w.querySelectorAll('li.tag-li')].map(li => clean(li.textContent)).join(', ')
}));
} else if (rec.length) {
page = 'recommended:' + txt(document, 'button.tab-list-active').replace(/\s*\(\d+\)/, '');
rows = [...rec].map(a => row(a.dataset.jobId, a.querySelector('a.jt-title-link')?.getAttribute('href'), {
title: txt(a, 'a.jt-title-link'), company: txt(a, '.subTitle'), rating: txt(a, 'span.typ-12Bold'), reviews: txt(a, '.reviewsCount'),
exp: txt(a, 'li.experience'), salary: txt(a, 'li.salary'), location: txt(a, 'li.location'),
posted: txt(a, '.jobTupleFooter .fw500'), tags: ''
}));
}
rows = rows.filter(r => /^\d+\|[^|]/.test(r));
let seen = 0, excluded = 0;
const exclude = RULES.exclude && new RegExp(RULES.exclude, 'i');
rows = rows.filter(r => {
const [id, title] = r.split('|');
if (RULES.seen.includes(`,${id},`)) { seen++; return false; }
if (exclude && exclude.test(title)) { excluded++; return false; }
return true;
});
const total = (body.match(/\d+\s*-\s*\d+\s+of\s+([\d,]+)/) || [])[1] ||
txt(document, 'button.tab-list-active').replace(/\D/g, '') || '?';
const lines = [`page: ${page} | total: ${total} | count: ${rows.length} | seen: ${seen} | excluded: ${excluded} | signals: ${signals.join(',') || 'none'}`, ...rows];
const chunks = [];
let cur = '';
for (const l of lines) {
if (cur && cur.length + l.length + 1 > LIMIT) { chunks.push(cur); cur = ''; }
cur += (cur ? '\n' : '') + l.slice(0, LIMIT);
}
if (cur) chunks.push(cur);
const k = Symbol.for('job-apply');
delete window[k];
Object.defineProperty(window, k, { value: { chunks: chunks.slice(1), i: 1, n: chunks.length }, configurable: true, writable: true });
return `[1/${chunks.length}]\n` + chunks[0];
})();
