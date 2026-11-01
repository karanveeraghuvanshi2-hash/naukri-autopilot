await (async () => {
for (let t = 0; t < 6000 && !document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img, input[type=password]'); t += 250)
await new Promise(r => setTimeout(r, 250));
const body = document.body ? document.body.innerText : '';
const overlays = [...document.querySelectorAll('[role=dialog], [role=alert], [class*=modal i], [class*=toast i], [class*=snackbar i], [class*=captcha i]')]
.filter(el => el.offsetParent).map(el => el.innerText).join(' ');
const focus = [document.title, overlays, body.length < 3000 ? body : ''].join(' ');
const loggedIn = !!document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img');
const challengeFrame = [...document.querySelectorAll('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare"], .g-recaptcha')].some(el => {
if (el.closest('.grecaptcha-badge')) return false;
const r = el.getBoundingClientRect(), s = getComputedStyle(el);
return r.width > 10 && r.height > 10 && s.visibility !== 'hidden' && s.display !== 'none';
});
const signals = [];
if (/\/nlogin\//.test(location.pathname) || document.querySelector('input[type=password]')) signals.push('login_page');
else if (!loggedIn) signals.push('logged_out');
if (challengeFrame ||
/captcha|verify (that )?you are (a )?human|are you a robot/i.test(focus)) signals.push('captcha');
if (/unusual (activity|traffic)|suspicious activity|automated (access|requests|queries)|temporarily (blocked|restricted)|account (has been )?(restricted|suspended|blocked)/i.test(focus)) signals.push('unusual_activity');
if (/access denied|too many requests|forbidden|\b(403|429)\b/i.test(focus)) signals.push('blocked');
if (/daily quota (expired|exceeded)|quota expired|daily (apply|application) limit/i.test(body)) signals.push('quota');
return JSON.stringify({ url: location.origin + location.pathname, title: document.title, loggedIn, signals });
})();
