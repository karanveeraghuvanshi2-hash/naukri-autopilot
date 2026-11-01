// Read-only safety check for any naukri.com page. Pass this whole file as the
// `text` of javascript_tool. It never clicks, types or fetches.
// Returns {url, title, loggedIn, signals}; any signal means stop (knowledge/safety.md).
await (async () => {
  // Wait (max 6 s) for the header so a page that is still loading doesn't read as logged out.
  for (let t = 0; t < 6000 && !document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img, input[type=password]'); t += 250)
    await new Promise(r => setTimeout(r, 250));
  const body = document.body ? document.body.innerText : '';
  // Overlays and short pages only, so a job description that mentions
  // "captcha" or "403" can't trigger a false stop.
  const overlays = [...document.querySelectorAll('[role=dialog], [role=alert], [class*=modal i], [class*=toast i], [class*=snackbar i], [class*=captcha i]')]
    .filter(el => el.offsetParent).map(el => el.innerText).join(' ');
  const focus = [document.title, overlays, body.length < 3000 ? body : ''].join(' ');
  const loggedIn = !!document.querySelector('.nI-gNb-drawer, img.nI-gNb-icon-img');
  // A captcha frame counts only when it is on screen: Google's invisible reCAPTCHA v3 loads hidden
  // frames (and a corner badge) on ordinary pages.
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
