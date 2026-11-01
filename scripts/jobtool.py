#!/usr/bin/env python3
"""jobtool: tracker, prefilter, pacing and run guards for the job-apply skills.

Stdlib only. `python3 scripts/jobtool.py <command> --help` explains each command.
Paths resolve from JOBTOOL_ROOT (default: this repo). JOBTOOL_NOW (ISO 8601)
fixes the clock, for tests.

Exit codes: 0 ok, 2 bad input or state or a refused attempt, 3 run blocked
(start) or a corrupt lock or state file, 4 page signals (prefilter): stop and
follow knowledge/safety.md, 5 the extractor's output doesn't add up (prefilter).
"""
import argparse
import copy
import csv
import json
import math
import os
import pathlib
import random
import re
import shutil
import sqlite3
import sys
import time
import tomllib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NAUKRI = "https://www.naukri.com"
STATUSES = ("new", "queued", "applied", "skipped", "skipped_unknown_question", "skipped_screener",
            "company_site_queued", "company_site_applied", "manual_needed", "failed")
FINAL = ("applied", "company_site_applied")  # a later status never overwrites these
ATTEMPTS = ("applied", "failed", "skipped_unknown_question", "skipped_screener")  # Apply was clicked: paced
CARD_FIELDS = ("id", "title", "company", "exp", "salary", "location", "posted",
               "rating", "reviews", "tags", "slug")
SLOTS = ("morning", "evening", "manual")
COOLDOWN_SIGNALS = ("captcha", "unusual_activity", "blocked", "quota", "warning")  # login_page, logged_out: none
RULES_SLOT = "const RULES = { seen: '', exclude: '' };"  # extract_cards.js line that `start` fills in per run
RECOMMENDED_PAGES = 2
BACKUPS_KEPT = 14

DEFAULTS = {
    "experience": {"career_start": "", "gap_months": 0, "min_slack": 1.0, "max_slack": 1.0},
    "salary": {"floor_lpa": 0},
    "location": {
        "office": [],
        "search_city": "",
        "remote": ["remote", "work from home", "wfh", "anywhere"],
    },
    "titles": {"exclude": []},
    "caps": {"per_day": 25, "per_run": 13, "evening_max": 15, "company_site_per_run": 5},
    "pace": {"min_gap_seconds": 60, "jitter_seconds": 60, "page_load_min_seconds": 10, "page_load_jitter_seconds": 10},
    "window": {"start": "08:00", "end": "22:00", "min_hours_between_runs": 3},
    "safety": {"cooldown_hours": 24, "max_consecutive_failures": 2, "lock_stale_hours": 3,
               "max_consecutive_jd_skips": 5, "retry_unknown_question": False},
    "search": {"job_age_days": 3, "max_pages": 8, "repost_days": 30},
    "digest": {"evening_after_hours": 20, "morning_catch_up_hours": 24},
    "targeting": {"target_roles": "", "other_roles": "", "core_stack": "", "avoid_stacks": "", "dealbreakers": "",
                  "consultancies": "penalize"},
    "scoring": {"threshold": 65, "queue_max_age_days": 7},
    "keyword_sets": [],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  source TEXT NOT NULL DEFAULT 'naukri',
  id TEXT NOT NULL,
  title TEXT, company TEXT, exp TEXT, salary TEXT, location TEXT, posted TEXT,
  rating TEXT, reviews TEXT, tags TEXT, url TEXT,
  found_via TEXT, keyword_group TEXT,
  status TEXT NOT NULL, reason TEXT, score INTEGER, score_notes TEXT,
  answers TEXT, recruiter_status TEXT, company_url TEXT,
  run_id TEXT, first_seen TEXT NOT NULL, updated_at TEXT NOT NULL, applied_at TEXT,
  PRIMARY KEY (source, id)
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, slot TEXT, dry_run INTEGER, budget INTEGER,
  started_at TEXT, finished_at TEXT, signal TEXT
);
CREATE TABLE IF NOT EXISTS events (ts TEXT, run_id TEXT, job_id TEXT, kind TEXT, detail TEXT);
"""


class Fail(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


# ---------- environment ----------

def root():
    return pathlib.Path(os.environ.get("JOBTOOL_ROOT") or pathlib.Path(__file__).resolve().parents[1])


def path(name):
    r = root()
    return {
        "db": r / "data" / "tracker.db",
        "state": r / "data" / "state.json",
        "lock": r / "data" / "run.lock",
        "runs": r / "data" / "runs",
        "exports": r / "data" / "exports",
        "prefs": r / "profile" / "preferences.toml",
        "answers": r / "profile" / "answers.md",
    }[name]


def lean():
    """True in a session started through the lean launcher (profile/run-settings.json sets NAUKRI_LEAN)."""
    return os.environ.get("NAUKRI_LEAN") == "1"


def now():
    fixed = os.environ.get("JOBTOOL_NOW")
    t = datetime.fromisoformat(fixed) if fixed else datetime.now(IST)
    return t.astimezone(IST).replace(microsecond=0)


def stamp(t):
    return t.isoformat()


def load_prefs(file=None, text=None):
    if text is None:
        file = pathlib.Path(file or path("prefs"))
        if not file.exists():
            raise Fail(f"missing {file}: run /naukri-setup (template: profile.example/preferences.toml)")
        text = file.read_text()
    prefs = copy.deepcopy(DEFAULTS)
    for key, value in tomllib.loads(text).items():
        if isinstance(value, dict) and isinstance(prefs.get(key), dict):
            prefs[key].update(value)
        else:
            prefs[key] = value
    loc = prefs["location"]
    if "ncr" in loc:  # files from before office/search_city: the same terms, searched in Delhi NCR
        loc["office"] = loc["office"] or loc["ncr"]
        loc["search_city"] = loc["search_city"] or "delhi-ncr"
    return prefs


def load_state():
    p = path("state")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except ValueError:
        raise Fail(f"blocked: {p} is corrupt; repair or delete it (cooldown and hold live there)", 3)


def save_state(state):
    p = path("state")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, p)


NEW_COLUMNS = (("det", "INTEGER"), ("retried_at", "TEXT"))  # added after the first release: migrate() adds them


def migrate(conn):
    have = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for name, kind in NEW_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
    conn.commit()


def db():
    if not path("db").exists():
        raise Fail("not initialized: run `python3 scripts/jobtool.py init` first")
    conn = sqlite3.connect(path("db"))
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def event(conn, kind, detail="", job_id=None, run_id=None):
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                 (stamp(now()), run_id or current_run_id(), job_id, kind, detail))


def read_lock():
    p = path("lock")
    if not p.exists():
        return None
    try:
        held = json.loads(p.read_text())
    except ValueError:
        held = None
    if not (isinstance(held, dict) and "run_id" in held and "started_at" in held):
        raise Fail(f"blocked: {p} is corrupt; check no run is active, then: python3 scripts/jobtool.py unlock", 3)
    return held


def current_run_id():
    held = read_lock()
    return held["run_id"] if held else None


def take_lock(run_id, t):
    try:
        fd = os.open(path("lock"), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise Fail("blocked: another run took the lock first", 3)
    with os.fdopen(fd, "w") as fh:
        json.dump({"run_id": run_id, "started_at": stamp(t)}, fh)


# ---------- parsing ----------

def _num(s):
    f = float(s)
    return int(f) if f.is_integer() else f


def parse_exp(text):
    """'5-10 Yrs' -> (5, 10); '10+ Yrs' -> (10, None); unknown -> (None, None)."""
    t = (text or "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:yrs?|years?)", t)
    if m:
        return _num(m[1]), _num(m[2])
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+\s*(?:yrs?|years?)", t)
    if m:
        return _num(m[1]), None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:yrs?|years?)", t)
    if m:
        return _num(m[1]), _num(m[1])
    return None, None


def parse_salary(text):
    """Salary range in INR lakhs per year, 'non_inr' for other currencies, None if hidden."""
    t = (text or "").lower().replace(",", "")
    if not t.strip() or "not disclosed" in t:
        return None
    if re.search(r"[$€£]|\b(usd|eur|gbp|aed|sgd|cad|aud)\b", t):
        return "non_inr"
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums:
        return None
    lo, hi = nums[0], nums[1] if len(nums) > 1 else nums[0]
    if re.search(r"\bcr\b|crore", t):
        factor = 100.0
    elif re.search(r"lac|lakh|lpa", t):
        factor = 1.0
    else:
        factor = 1e-5  # plain rupees
    if re.search(r"per month|/ ?month|\bpm\b|monthly", t):
        factor *= 12
    return round(lo * factor, 2), round(hi * factor, 2)


def _has_term(text, term):
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) is not None


def location_ok(text, prefs):
    """True when the job is remote or names one of the office terms (unknown passes)."""
    t = (text or "").lower()
    if not t.strip():
        return True
    t = re.sub(r"temp(orarily|\.)?\s*(wfh|work from home)", "", t)  # temporary WFH = office later
    terms = prefs["location"]["remote"] + prefs["location"]["office"]
    return any(_has_term(t, term) for term in terms)


def title_excluded(title, prefs):
    t = (title or "").lower()
    return next((term for term in prefs["titles"]["exclude"] if _has_term(t, term)), None)


def title_pattern(prefs):
    """title_excluded as one regular expression, for the page-side filter in extract_cards.js."""
    terms = prefs["titles"]["exclude"]
    if not terms:
        return ""
    return "(?<![a-z0-9])(?:" + "|".join(re.escape(x.lower()) for x in terms) + ")(?![a-z0-9])"


def total_years(prefs, t):
    start = prefs["experience"].get("career_start")
    if not start:
        return None
    y, m = (int(x) for x in start.split("-")[:2])
    months = (t.year - y) * 12 + (t.month - m) - int(prefs["experience"].get("gap_months", 0))
    return round(months / 12, 1)


def parse_rows(text):
    """Read extract_cards.js output (chunk markers and headers included)."""
    headers, cards = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"\[\d+/\d+\]", line):
            continue
        if line.startswith("page:"):
            headers.append({k.strip(): v.strip() for k, v in
                            (part.split(":", 1) for part in line.split("|") if ":" in part)})
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != len(CARD_FIELDS) or not re.fullmatch(r"\d{6,}", parts[0]):
            continue
        c = dict(zip(CARD_FIELDS, parts))
        slug = c.pop("slug")
        c["url"] = NAUKRI + slug if slug.startswith("/") else f"{NAUKRI}/job-listings-{slug}-{c['id']}"
        cards.append(c)
    return headers, cards


def card_problem(headers, cards):
    """Why this extractor output can't be trusted, or None. A changed page must not pass for a thin pool."""
    if not headers:
        return "no extractor header (send extract_cards.js output, not a shortened probe)"
    if any(h.get("page") == "unknown" for h in headers):
        return "page: unknown (no job cards found: a search with no results, or a changed layout)"
    want = sum(int(h["count"]) for h in headers if h.get("count", "").isdigit())
    if want != len(cards):
        return f"header says {want} cards, {len(cards)} parsed"
    return None


def reject_reason(c, prefs, total):
    """Why a card fails the hard rules, or None when it goes on to scoring."""
    term = title_excluded(c["title"], prefs)
    if term:
        return f"title: {term}"
    if not location_ok(c["location"], prefs):
        return f"location: {c['location']}"
    lo, hi = parse_exp(c["exp"])
    exp = prefs["experience"]
    if total is not None and lo is not None and lo > total + exp["min_slack"]:
        return f"experience: {c['exp']} starts above {total} yrs"
    if total is not None and hi is not None and hi < total - exp["max_slack"]:
        return f"experience: {c['exp']} ends below {total} yrs"
    salary = parse_salary(c["salary"])
    if isinstance(salary, tuple) and salary[1] < prefs["salary"]["floor_lpa"]:
        return f"salary: tops out at {salary[1]:g} LPA"
    return None


def posted_days(text):
    """Age of a card's 'posted' text in days, or None when it says nothing."""
    t = (text or "").lower()
    if re.search(r"just now|today|hour|minute|few", t):
        return 0
    m = re.search(r"(\d+)\+?\s*day", t)
    return int(m[1]) if m else None


def det_points(c, prefs, total):
    """The 35 points of the score that need no judgement: experience 15, location and mode 10, signals 10."""
    lo, hi = parse_exp(c["exp"])
    slack = prefs["experience"]
    if total is None or (lo is None and hi is None):
        exp = 8
    elif (lo is None or lo <= total) and (hi is None or total <= hi):
        exp = 15
    elif (lo is not None and 0 < lo - total <= slack["min_slack"]) or (hi is not None and 0 < total - hi <= slack["max_slack"]):
        exp = 8
    else:
        exp = 0

    loc_text = re.sub(r"temp(orarily|\.)?\s*(wfh|work from home)", "", (c["location"] or "").lower())
    if any(_has_term(loc_text, term) for term in prefs["location"]["remote"]):
        loc = 10
    elif any(_has_term(loc_text, term) for term in prefs["location"]["office"]):
        loc = 8 if "hybrid" in loc_text else 6
    else:
        loc = 5

    try:
        rating = float(c["rating"])
        rate = 4 if rating >= 4.0 else 2 if rating >= 3.5 else 0
    except (TypeError, ValueError):
        rate = 1
    days = posted_days(c["posted"])
    fresh = 1 if days is None else 3 if days <= 3 else 1 if days <= 7 else 0
    salary = parse_salary(c["salary"])
    sal = 2 if not isinstance(salary, tuple) else 3 if salary[1] >= prefs["salary"]["floor_lpa"] else 0
    return {"exp": exp, "loc": loc, "sig": rate + fresh + sal, "total": exp + loc + rate + fresh + sal}


def repost_key(c):
    norm = lambda x: re.sub(r"[^a-z0-9]+", " ", (x or "").lower()).strip()
    return norm(c["company"]) + "|" + norm(c["title"])


def recent_originals(conn, prefs, t):
    """{repost key: job id} for jobs first seen inside the repost window that the prefilter let through."""
    cutoff = stamp(t - timedelta(days=prefs["search"]["repost_days"]))
    rows = conn.execute("SELECT id, company, title FROM jobs WHERE first_seen >= ?"
                        " AND (reason IS NULL OR reason NOT LIKE 'prefilter%') ORDER BY first_seen", (cutoff,))
    return {repost_key(r): r["id"] for r in rows}


def floor_seconds(prefs):
    """Pause between two Naukri page loads, slept out inside the command that closes a page."""
    p = prefs["pace"]
    return p["page_load_min_seconds"] + random.randint(0, p["page_load_jitter_seconds"])


def digest_line(prefs, state, slot, t):
    last = state.get("last_digest_at")
    d = prefs["digest"]
    hours = d["morning_catch_up_hours"] if slot == "morning" else d["evening_after_hours"]
    due = not last or (t - datetime.fromisoformat(last)).total_seconds() / 3600 >= hours
    return f"digest: {'due' if due else 'skip'} | last {last or 'never'}"


# ---------- run state ----------

def today_applied(conn, t):
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied' AND applied_at LIKE ?",
                        (t.date().isoformat() + "%",)).fetchone()[0]


def run_applied(conn, run_id):
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied' AND run_id=?",
                        (run_id,)).fetchone()[0]


def slot_budget(prefs, slot, applied_today):
    caps = prefs["caps"]
    left = max(0, caps["per_day"] - applied_today)
    return min(caps["evening_max"] if slot == "evening" else caps["per_run"], left)


def in_window(prefs, t):
    w = prefs["window"]
    return w["start"] <= t.strftime("%H:%M") < w["end"]


def cooldown_until(state, t):
    until = state.get("cooldown_until")
    return datetime.fromisoformat(until) if until and datetime.fromisoformat(until) > t else None


def set_cooldown(state, prefs, signal, hours=None):
    until = now() + timedelta(hours=hours or prefs["safety"]["cooldown_hours"])
    state.update(cooldown_until=stamp(until), cooldown_signal=signal)
    return until


def pending_answers():
    p = path("answers")
    if not p.exists():
        return 0
    count, inside = 0, False
    for line in p.read_text().splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("pending review")
        elif inside and re.match(r"\s*- \[ \]", line):
            count += 1
    return count


def keyword_slug(keyword):
    return re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")


def next_searches(prefs, state, total, limit):
    """This run's search URLs: one keyword set per run, rotating; returns [(group, mode, url)]."""
    sets = prefs["keyword_sets"]
    if not sets:
        return []
    rot = state.setdefault("rotation", {"group_index": 0, "offsets": {}})
    group = sets[rot["group_index"] % len(sets)]
    rot["group_index"] += 1
    search = prefs["search"]
    params = f"jobAge={search['job_age_days']}" + (f"&experience={round(total)}" if total is not None else "")
    city = keyword_slug(prefs["location"]["search_city"])
    specs = []
    for kw in group["keywords"]:
        slug = keyword_slug(kw)
        specs.append((group["group"], "remote", f"{NAUKRI}/{slug}-jobs?wfhType=2&{params}"))
        if city:
            specs.append((group["group"], "office", f"{NAUKRI}/{slug}-jobs-in-{city}?{params}"))
    take = min(max(limit, 0), len(specs))
    start = rot["offsets"].get(group["group"], 0) % len(specs)
    rot["offsets"][group["group"]] = start + take
    return [specs[(start + i) % len(specs)] for i in range(take)]


# ---------- commands ----------

def cmd_init(args):
    for d in (path("runs"), path("exports")):
        d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path("db"))
    conn.executescript(SCHEMA)
    migrate(conn)
    if not path("state").exists():
        save_state({})
    print(f"initialized {path('db').parent}")
    return 0


def write_run_extractor(conn, prefs, t, run_id):
    """data/runs/<run_id>/extract_cards.js: the packed extractor with this run's seen ids and title rule.

    The page then returns only cards worth scoring, so the model relays less text. Private (titles
    come from preferences.toml). Rows the title rule rejects need no seen entry.
    """
    src = root() / "scripts" / "browser" / "packed" / "extract_cards.js"
    if not src.exists():
        return
    text = src.read_text()
    if RULES_SLOT not in text:
        raise Fail(f"{src} has no RULES line; run: python3 scripts/jobtool.py pack")
    cutoff = stamp(t - timedelta(days=prefs["scoring"]["queue_max_age_days"]))
    seen = [r["id"] for r in conn.execute("SELECT id, title FROM jobs WHERE first_seen >= ?", (cutoff,))
            if not title_excluded(r["title"], prefs)]
    rules = {"seen": "," + ",".join(seen) + ",", "exclude": title_pattern(prefs)}
    (path("runs") / run_id / "extract_cards.js").write_text(text.replace(RULES_SLOT, f"const RULES = {json.dumps(rules)};"))


def cmd_status(args):
    print(f"lean: {'yes' if lean() else 'no'}")  # first, so /naukri-setup's guard works before any file exists
    try:
        if not path("db").exists():
            print("jobtool: not initialized (run: python3 scripts/jobtool.py init)")
            return 0
        prefs, state, conn, t = load_prefs(), load_state(), db(), now()
        w = prefs["window"]
        done = today_applied(conn, t)
        cd = cooldown_until(state, t)
        lock = read_lock()
        last = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        counts = dict(conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())
        print(f"now: {t:%Y-%m-%d %H:%M} IST | window {w['start']}-{w['end']} ({'open' if in_window(prefs, t) else 'closed'})")
        print(f"applied today: {done}/{prefs['caps']['per_day']} | budget morning {slot_budget(prefs, 'morning', done)}, evening {slot_budget(prefs, 'evening', done)}")
        print(f"cooldown: {'until ' + stamp(cd) + ' (' + state.get('cooldown_signal', '?') + ')' if cd else 'none'}")
        print(f"hold: {'on' if state.get('hold') else 'off'}")
        print(f"lock: {'held by ' + lock['run_id'] + ' since ' + lock['started_at'] if lock else 'free'}")
        print(f"last run: {last['run_id'] + ' (finished ' + (last['finished_at'] or 'no') + ')' if last else 'never'}")
        print(f"jobs: queued {counts.get('queued', 0)} | new {counts.get('new', 0)} | company-site queued "
              f"{counts.get('company_site_queued', 0)} | manual needed {counts.get('manual_needed', 0)}")
        print(f"pending answers: {pending_answers()}")
    except Exception as e:  # status feeds a skill's context: report, never fail
        print(f"jobtool status error: {e}")
    return 0


def cmd_start(args):
    prefs, state, conn, t = load_prefs(), load_state(), db(), now()
    w, safety = prefs["window"], prefs["safety"]
    if state.get("hold"):
        raise Fail("blocked: hold is on (python3 scripts/jobtool.py hold off)", 3)
    if not lean():
        raise Fail("blocked: NAUKRI_LEAN is not set; start the session with ./naukri", 3)
    if not in_window(prefs, t):
        raise Fail(f"blocked: {t:%H:%M} is outside the run window {w['start']}-{w['end']} IST", 3)
    cd = cooldown_until(state, t)
    if cd:
        raise Fail(f"blocked: cooldown until {stamp(cd)} after {state.get('cooldown_signal')}", 3)
    notes, stale = [], None
    held = read_lock()
    if held:
        age = t - datetime.fromisoformat(held["started_at"])
        if age < timedelta(hours=safety["lock_stale_hours"]):
            raise Fail(f"blocked: lock held by {held['run_id']} since {held['started_at']}", 3)
        stale = held["run_id"]
    # Only runs that could apply count: a dry run must not block the scheduled one after it.
    last = conn.execute("SELECT run_id, started_at FROM runs WHERE dry_run=0 ORDER BY started_at DESC LIMIT 1").fetchone()
    gap = timedelta(hours=w["min_hours_between_runs"])
    in_gap = last and t - datetime.fromisoformat(last["started_at"]) < gap
    if in_gap and not args.force:
        raise Fail(f"blocked: recent run {last['run_id']} started {last['started_at']}; "
                   f"runs need a {w['min_hours_between_runs']} h gap (--force for a manual run)", 3)
    if args.check:
        print("ok")
        return 0

    run_id = f"{t:%Y%m%d-%H%M}-{args.slot}"
    if conn.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
        run_id += f"-{random.randint(100, 999)}"
    if stale:
        path("lock").unlink(missing_ok=True)
        notes.append(f"stale lock from {stale} replaced")
        event(conn, "stale_lock", stale, run_id=run_id)
    take_lock(run_id, t)
    if in_gap:
        event(conn, "force", f"inside the gap after {last['run_id']}", run_id=run_id)
    done = today_applied(conn, t)
    budget = 0 if args.dry_run else slot_budget(prefs, args.slot, done)
    conn.execute("INSERT INTO runs (run_id, slot, dry_run, budget, started_at) VALUES (?,?,?,?,?)",
                 (run_id, args.slot, int(args.dry_run), budget, stamp(t)))
    (path("runs") / run_id).mkdir(parents=True, exist_ok=True)
    write_run_extractor(conn, prefs, t, run_id)
    state["consecutive_failures"] = 0
    state["consecutive_jd_skips"] = 0
    state.pop("rail_refused", None)
    total = total_years(prefs, t)
    pages = prefs["search"]["max_pages"] + (RECOMMENDED_PAGES if args.slot == "morning" else 0)
    searches = next_searches(prefs, state, total, pages - RECOMMENDED_PAGES)
    save_state(state)
    event(conn, "run_start", f"slot {args.slot} budget {budget}", run_id=run_id)
    conn.commit()

    counts = dict(conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())
    company_budget = 0 if args.dry_run else prefs["caps"]["company_site_per_run"]
    print(f"run {run_id} | budget: {budget} | company-site budget: {company_budget} | dry run: {'yes' if args.dry_run else 'no'}")
    print(f"applied today: {done}/{prefs['caps']['per_day']} | queued: {counts.get('queued', 0)} | new (unscored): {counts.get('new', 0)}")
    print(f"experience: {total} yrs" if total is not None else "experience: unknown (set career_start in [experience])")
    for key, value in prefs["targeting"].items():
        if value:
            print(f"targeting.{key}: {value}")
    for n in notes:
        print(f"note: {n}")
    if args.slot == "morning" and state.get("last_refresh_date") != t.date().isoformat():
        print(f"refresh: due (variant {state.get('next_variant', 1)})")
    print(digest_line(prefs, state, args.slot, t))
    week = f"{t.isocalendar().year}-W{t.isocalendar().week:02d}"
    if args.slot == "evening" and t.weekday() == 6 and state.get("last_weekly_week") != week:
        print("weekly: due")
    print(f"discovery (max {pages} page loads): recommended tabs Profile, Preferences; then")
    for group, mode, url in searches:
        print(f"search {group} {mode} {url}")
    return 0


def cmd_finish(args):
    prefs, state, conn, t = load_prefs(), load_state(), db(), now()
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (args.run_id,)).fetchone()
    if not run:
        raise Fail(f"unknown run {args.run_id}")
    conn.execute("UPDATE runs SET finished_at=?, signal=? WHERE run_id=?", (stamp(t), args.signal, args.run_id))
    lines = []
    if args.signal:
        until = cooldown_until(state, t)  # prefilter or `signal` may have started it already
        if not until:
            until = set_cooldown(state, prefs, args.signal)
            save_state(state)
        event(conn, "signal", args.signal, run_id=args.run_id)
        lines.append(f"cooldown until {stamp(until)} ({args.signal})")
    event(conn, "run_finish", run_id=args.run_id)
    conn.commit()
    if current_run_id() == args.run_id:
        path("lock").unlink()
    counts = conn.execute("SELECT status, COUNT(*) FROM jobs WHERE run_id=? GROUP BY status ORDER BY status",
                          (args.run_id,)).fetchall()
    csv_path = export_csv(conn)
    try:
        backup_path = backup(conn, t)
        lines.append(f"backup: {backup_path}")
    except (OSError, sqlite3.Error) as e:  # the run is over either way
        lines.append(f"backup FAILED: {e}")
    print(f"finished {args.run_id}: " + (", ".join(f"{s} {n}" for s, n in counts) or "no jobs touched"))
    for line in lines:
        print(line)
    print(f"csv: {csv_path}")
    return 0


def cmd_signal(args):
    """Start the cooldown the moment a signal shows, so a crash before `finish` can't lose it."""
    if args.name not in COOLDOWN_SIGNALS:
        raise Fail(f"{args.name} starts no cooldown; use one of: {', '.join(COOLDOWN_SIGNALS)}")
    prefs, state, conn = load_prefs(), load_state(), db()
    until = set_cooldown(state, prefs, args.name)
    save_state(state)
    event(conn, "signal", args.name)
    conn.commit()
    print(f"cooldown until {stamp(until)} ({args.name})")
    return 0


def cmd_prefilter(args):
    prefs, conn, t = load_prefs(), db(), now()
    text = sys.stdin.read() if args.cards == "-" else pathlib.Path(args.cards).read_text()
    headers, cards = parse_rows(text)
    signals = sorted({s for h in headers for s in h.get("signals", "none").split(",") if s not in ("", "none")})
    if signals:
        hits = [s for s in signals if s in COOLDOWN_SIGNALS]
        if hits:
            state = load_state()
            set_cooldown(state, prefs, hits[0])
            save_state(state)
            event(conn, "signal", ",".join(hits))
            conn.commit()
        print(f"STOP: page signals {', '.join(signals)}; nothing recorded. Follow knowledge/safety.md.")
        return 4
    problem = card_problem(headers, cards)
    if problem:
        event(conn, "extractor_problem", f"{args.via}: {problem}")
        conn.commit()
        print(f"BROKEN: {problem}; nothing recorded.")
        return 5
    total = total_years(prefs, t)
    via = args.via or (headers[0].get("page") if headers else None)
    run_id = current_run_id()
    originals = recent_originals(conn, prefs, t)
    new, rejected = [], {}
    seen = sum(int(h.get("seen", 0)) for h in headers)  # filtered in the page
    excluded = sum(int(h.get("excluded", 0)) for h in headers)
    for c in cards:
        if conn.execute("SELECT 1 FROM jobs WHERE source='naukri' AND id=?", (c["id"],)).fetchone():
            seen += 1
            continue
        reason = reject_reason(c, prefs, total)
        key = repost_key(c)
        if not reason and key in originals:
            reason = f"repost: of {originals[key]}"
        det = None if reason else det_points(c, prefs, total)["total"]
        conn.execute(
            "INSERT INTO jobs (id, title, company, exp, salary, location, posted, rating, reviews, tags, url,"
            " found_via, keyword_group, status, reason, det, run_id, first_seen, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["id"], c["title"], c["company"], c["exp"], c["salary"], c["location"], c["posted"],
             c["rating"], c["reviews"], c["tags"], c["url"], via, args.group,
             "skipped" if reason else "new", f"prefilter {reason}" if reason else None, det,
             run_id, stamp(t), stamp(t)))
        if reason:
            kind = reason.split(":")[0]
            rejected[kind] = rejected.get(kind, 0) + 1
        else:
            originals[key] = c["id"]
            c["det"] = det
            new.append(c)
    conn.commit()
    summary = f"new {len(new)} | seen {seen} | rejected {sum(rejected.values())}"
    if rejected:
        summary += ": " + ", ".join(f"{k} {v}" for k, v in sorted(rejected.items()))
    if excluded:
        summary += f" | page-excluded {excluded}"
    print(summary)
    for c in new:
        print("|".join(c[k] for k in ("id", "title", "company", "exp", "salary", "location", "posted", "rating", "tags"))
              + f"|d{c['det']}")
    if run_id and not args.no_floor:
        time.sleep(floor_seconds(prefs))
    return 0


def cmd_rescreen(args):
    """Rows the prefilter rejected under older rules that today's rules would let through."""
    prefs, conn, t = load_prefs(), db(), now()
    cutoff = stamp(t - timedelta(days=prefs["scoring"]["queue_max_age_days"]))
    total = total_years(prefs, t)
    originals = recent_originals(conn, prefs, t)
    freed = []
    for r in conn.execute("SELECT * FROM jobs WHERE status='skipped' AND reason LIKE 'prefilter %'"
                          " AND reason NOT LIKE 'prefilter repost%' AND first_seen >= ? ORDER BY first_seen",
                          (cutoff,)).fetchall():
        c = dict(r)
        if reject_reason(c, prefs, total) or repost_key(c) in originals:
            continue
        originals[repost_key(c)] = c["id"]
        c["det"] = det_points(c, prefs, total)["total"]
        freed.append(c)
    if not args.apply:
        print(f"would free {len(freed)} (add --apply)")
        for c in freed:
            print(f"{c['id']}|{c['title']}|{c['company']}|{c['reason']}")
        return 0
    for c in freed:
        conn.execute("UPDATE jobs SET status='new', reason=NULL, det=?, updated_at=? WHERE source='naukri' AND id=?",
                     (c["det"], stamp(t), c["id"]))
        event(conn, "rescreen", c["reason"], job_id=c["id"])
    conn.commit()
    print(f"freed {len(freed)}")
    for c in freed:
        print("|".join(c[k] or "" for k in ("id", "title", "company", "exp", "salary", "location", "posted", "rating", "tags"))
              + f"|d{c['det']}")
    return 0


def cmd_score(args):
    prefs, conn, t = load_prefs(), db(), now()
    try:
        items = json.loads(sys.stdin.read() if args.json == "-" else args.json)
    except json.JSONDecodeError as e:
        raise Fail(f"bad --json: {e}")
    items = [items] if isinstance(items, dict) else items
    rows = {str(i["id"]): conn.execute("SELECT status, det FROM jobs WHERE source='naukri' AND id=?", (str(i["id"]),)).fetchone()
            for i in items}
    unknown = [str(k) for k, r in rows.items() if r is None]
    final = [str(k) for k, r in rows.items() if r is not None and r["status"] in FINAL]
    if unknown or final:
        raise Fail("not scored: " + "; ".join(filter(None, [
            unknown and "unknown " + ", ".join(unknown), final and "already applied " + ", ".join(final)])))
    out_of_range = [str(i["id"]) for i in items if "model" in i and not 0 <= int(i["model"]) <= 65]
    if out_of_range:
        raise Fail("model part must be 0-65 (role 35 + skills 30): " + ", ".join(out_of_range))
    threshold = prefs["scoring"]["threshold"]
    queued = skipped = 0
    for i in items:
        if "model" in i:  # the model scores role and skills; jobtool adds the deterministic points
            det = rows[str(i["id"])]["det"] or 0
            score = int(i["model"]) + det
            notes = f"{i['why']} | det {det}" if i.get("why") else f"det {det}"
        else:
            score, notes = int(i["score"]), i.get("why")
        status = "queued" if score >= threshold else "skipped"
        conn.execute("UPDATE jobs SET status=?, reason=?, score=?, score_notes=?, updated_at=? WHERE source='naukri' AND id=?",
                     (status, None if status == "queued" else f"score {score} < {threshold}",
                      score, notes, stamp(t), str(i["id"])))
        queued += status == "queued"
        skipped += status == "skipped"
    conn.commit()
    print(f"queued {queued} | skipped {skipped} (below {threshold})")
    return 0


def cmd_queue(args):
    prefs, conn, t = load_prefs(), db(), now()
    cutoff = stamp(t - timedelta(days=prefs["scoring"]["queue_max_age_days"]))
    conn.execute("UPDATE jobs SET status='skipped', reason='stale: queued too long', updated_at=?"
                 " WHERE status='queued' AND first_seen < ?", (stamp(t), cutoff))
    conn.commit()
    rows = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY score DESC, first_seen DESC LIMIT ?",
                        (args.limit,)).fetchall()
    for r in rows:
        print(f"{r['id']}|{r['score']}|{r['title']}|{r['company']}|{r['location']}|{r['url']}")
    return 0


def norm_question(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def approved_questions():
    """Normalized question patterns under 'Approved' in the answer bank ('- pattern → answer')."""
    p = path("answers")
    found, inside = [], False
    for line in (p.read_text().splitlines() if p.exists() else []):
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("approved")
        elif inside and line.lstrip().startswith("- ") and "→" in line:
            found.append(norm_question(line.lstrip()[2:].split("→")[0]))
    return [q for q in found if len(q) >= 6]


def cmd_requeue(args):
    prefs, conn, t = load_prefs(), db(), now()
    if args.questions:
        if not prefs["safety"]["retry_unknown_question"]:
            raise Fail("requeue --questions is switched off: set retry_unknown_question = true under [safety] "
                       "in profile/preferences.toml once the abandon tests pass (knowledge/safety.md)")
        approved, count = approved_questions(), 0
        for r in conn.execute("SELECT id, reason FROM jobs WHERE status='skipped_unknown_question'"
                              " AND retried_at IS NULL").fetchall():
            q = norm_question(r["reason"])
            if q and any(a in q or q in a for a in approved):
                conn.execute("UPDATE jobs SET status='queued', reason=NULL, retried_at=?, updated_at=?"
                             " WHERE source='naukri' AND id=?", (stamp(t), stamp(t), r["id"]))
                count += 1
        conn.commit()
        print(f"requeued {count}")
        return 0
    if args.min_score is None:
        raise Fail("requeue needs --min-score N or --questions")
    cur = conn.execute("UPDATE jobs SET status='queued', reason=NULL, updated_at=?"
                       " WHERE status='skipped' AND reason LIKE 'score %' AND score >= ?", (stamp(t), args.min_score))
    conn.commit()
    print(f"requeued {cur.rowcount}")
    return 0


def cmd_audit_answers(args):
    """List screener answers that name no source (the bank, or 'derived: <how>')."""
    conn, bad = db(), []
    for r in conn.execute("SELECT id, company, answers FROM jobs WHERE answers IS NOT NULL ORDER BY first_seen"):
        for a in json.loads(r["answers"]):
            src = str(a.get("source") or "").strip()
            if not (src == "bank" or (src.startswith("derived:") and src[8:].strip())):
                bad.append(f"{r['id']}|{r['company']}|{a.get('question')}|source: {src or 'none'}")
    print("\n".join(bad + [f"unsourced answers: {len(bad)}"]))
    return 0


def cmd_hold(args):
    state = load_state()
    if args.action in ("on", "off"):
        state["hold"] = args.action == "on"
        save_state(state)
    print(f"hold: {'on' if state.get('hold') else 'off'}")
    return 0


def attempt_refusal(prefs, state, conn, t, row):
    """Why this attempt breaks a run rail, or None."""
    line = pace_line(prefs, state, conn, t)
    if line.startswith("stop "):
        return line[5:]
    return None if row["status"] == "queued" else f"job is {row['status']}, not queued"


def cmd_update(args):
    prefs, state, conn, t = load_prefs(), load_state(), db(), now()
    row = conn.execute("SELECT * FROM jobs WHERE source='naukri' AND id=?", (args.id,)).fetchone()
    if not row:
        raise Fail(f"unknown job {args.id}")
    if args.status and args.status not in STATUSES:
        raise Fail(f"unknown status {args.status}; use one of: {', '.join(STATUSES)}")
    if args.status and row["status"] in FINAL and args.status != row["status"]:
        raise Fail(f"job {args.id} is already {row['status']}; status kept")
    if args.status in ATTEMPTS:
        why = attempt_refusal(prefs, state, conn, t, row)
        if args.override is not None:
            event(conn, "override", f"{args.status}: {why or 'no rail hit'}: {args.override}", job_id=args.id)
        elif why:
            if current_run_id():
                state["rail_refused"] = args.id
                save_state(state)
            event(conn, "rail_refused", f"{args.status}: {why}", job_id=args.id)
            conn.commit()
            raise Fail(f"REFUSED {args.id}: {why}. Nothing recorded. If Apply was clicked, name this job in the "
                       "report's Needs you, then end the run.")
    fields = {"updated_at": stamp(t)}
    if args.answers is not None:
        raw = sys.stdin.read() if args.answers == "-" else args.answers
        try:
            fields["answers"] = json.dumps(json.loads(raw), ensure_ascii=False)
        except json.JSONDecodeError as e:
            raise Fail(f"bad --answers JSON: {e}")
    for name in ("reason", "recruiter_status", "company_url"):
        if getattr(args, name) is not None:
            fields[name] = getattr(args, name)
    run_id = current_run_id()
    reconciled = args.recruiter_status and not args.status and row["status"] not in FINAL
    if reconciled:  # Naukri lists it, so it was sent, whatever the tracker believed
        fields.update(status="applied", applied_at=row["updated_at"])
        event(conn, "reconcile", f"was {row['status']}", job_id=args.id)
    if args.status:
        fields["status"] = args.status
        if run_id:
            fields["run_id"] = run_id
        if args.status == "applied":
            fields["applied_at"] = stamp(t)
            state["consecutive_failures"] = 0
        if args.status == "failed":
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        if args.status == "skipped" and (args.reason or "").startswith("jd:"):
            state["consecutive_jd_skips"] = state.get("consecutive_jd_skips", 0) + 1
        elif args.status in ATTEMPTS or args.status == "company_site_queued":
            state["consecutive_jd_skips"] = 0
        if args.status in ATTEMPTS:
            p = prefs["pace"]
            gap = p["min_gap_seconds"] + random.randint(0, p["jitter_seconds"])
            state["next_allowed_at"] = stamp(t + timedelta(seconds=gap))
        save_state(state)
    conn.execute(f"UPDATE jobs SET {', '.join(k + '=?' for k in fields)} WHERE source='naukri' AND id=?",
                 (*fields.values(), args.id))
    event(conn, "update", json.dumps({k: v for k, v in fields.items() if k != "updated_at"}), job_id=args.id)
    conn.commit()
    print(f"{args.id}: " + ", ".join(f"{k} {v}" for k, v in fields.items() if k not in ("updated_at", "answers"))
          + (" (answers saved)" if "answers" in fields else ""))
    if reconciled:
        print(f"reconciled: was {row['status']}, Naukri shows it as sent")
    if run_id and args.status in ATTEMPTS:  # sleeping here saves the run a turn per application
        time.sleep(max(0, math.ceil((datetime.fromisoformat(state["next_allowed_at"]) - now()).total_seconds())))
        t = now()
    elif args.status and run_id and not args.no_floor:
        time.sleep(floor_seconds(prefs))  # the pause before the next page load costs the run no extra turn
        t = now()
    if args.status in ATTEMPTS:
        print(pace_line(prefs, state, conn, t))
    return 0


def pace_line(prefs, state, conn, t):
    """'go', 'wait <seconds>' or 'stop <reason>' for the next application."""
    cd = cooldown_until(state, t)
    if cd:
        return f"stop cooldown until {stamp(cd)}"
    run_id = current_run_id()
    run = run_id and conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        return "stop no active run (start one first)"
    if run["dry_run"]:
        return "stop dry run"
    if state.get("rail_refused"):
        return f"stop attempt refused for job {state['rail_refused']}"
    failures, limit = state.get("consecutive_failures", 0), prefs["safety"]["max_consecutive_failures"]
    if failures >= limit:
        return f"stop {failures} consecutive failures"
    skips, skip_limit = state.get("consecutive_jd_skips", 0), prefs["safety"]["max_consecutive_jd_skips"]
    if skips >= skip_limit:
        return f"stop {skips} final-check skips in a row"
    done = run_applied(conn, run_id)
    if done >= run["budget"]:
        return f"stop run budget used ({done}/{run['budget']})"
    day, cap = today_applied(conn, t), prefs["caps"]["per_day"]
    if day >= cap:
        return f"stop daily cap reached ({day}/{cap})"
    nxt = state.get("next_allowed_at")
    wait = math.ceil((datetime.fromisoformat(nxt) - t).total_seconds()) if nxt else 0
    return f"wait {wait} | run {done}/{run['budget']} | today {day}/{cap}" if wait > 0 else \
        f"go | run {done}/{run['budget']} | today {day}/{cap}"


def cmd_pace(args):
    prefs, conn = load_prefs(), db()
    line = pace_line(prefs, load_state(), conn, now())
    if args.job and not line.startswith("stop "):
        row = conn.execute("SELECT status FROM jobs WHERE source='naukri' AND id=?", (args.job,)).fetchone()
        if not row or row["status"] != "queued":
            print(f"stop job {args.job} is {row['status'] if row else 'unknown'}, not queued")
            return 0
    for _ in range(3):  # --wait: sleep out the gap, then report again
        if not (args.wait and line.startswith("wait ")):
            break
        time.sleep(int(line.split()[1]))
        line = pace_line(prefs, load_state(), conn, now())
    print(line)
    return 0


def cmd_cooldown(args):
    prefs, state, conn = load_prefs(), load_state(), db()
    if args.action == "set":
        until = set_cooldown(state, prefs, args.signal or "manual", args.hours)
        event(conn, "cooldown", f"{args.signal} until {stamp(until)}")
        print(f"cooldown until {stamp(until)}")
    elif args.action == "clear":
        state.pop("cooldown_until", None)
        state.pop("cooldown_signal", None)
        event(conn, "cooldown_clear")
        print("cooldown cleared")
    else:
        cd = cooldown_until(state, now())
        print(f"cooldown until {stamp(cd)} ({state.get('cooldown_signal')})" if cd else "no cooldown")
    save_state(state)
    conn.commit()
    return 0


def lock_owner():
    """The lock's run id; '?' for a corrupt lock; None without a lock."""
    try:
        held = read_lock()
    except Fail:
        return "?"
    return held["run_id"] if held else None


def cmd_unlock(args):
    owner = lock_owner()
    if owner:
        path("lock").unlink()
        conn = db()
        event(conn, "unlock", owner, run_id=owner)
        conn.commit()
        print(f"removed lock of {owner}")
    else:
        print("no lock")
    return 0


def cmd_reap(args):
    """Close a run its process left open. Only the launcher calls this, after `claude` has exited."""
    owner = lock_owner()
    if not owner:
        print("clean")
        return 0
    conn = db()
    conn.execute("UPDATE runs SET finished_at=? WHERE run_id=? AND finished_at IS NULL", (stamp(now()), owner))
    event(conn, "run_crashed", run_id=owner)
    conn.commit()
    path("lock").unlink()
    print(f"reaped {owner}")
    return 0


def backup(conn, t):
    """Copy the tracker and the single-copy private files into data/backups/<date>; keep the newest 14."""
    base = root() / "data" / "backups"
    day = base / f"{t:%Y%m%d}"
    day.mkdir(parents=True, exist_ok=True)
    dest = sqlite3.connect(day / "tracker.db")
    with dest:
        conn.backup(dest)
    dest.close()
    for name in ("answers", "prefs", "state"):
        if path(name).exists():
            shutil.copy2(path(name), day)
    for old in sorted(d for d in base.iterdir() if d.is_dir())[:-BACKUPS_KEPT]:
        shutil.rmtree(old)
    return day


def cmd_backup(args):
    print(f"backup: {backup(db(), now())}")
    return 0


def cmd_report(args):
    """Write data/runs/<run_id>/report.md from the tracker, with the model's notes on top, so counts can't drift."""
    prefs, state, conn, t = load_prefs(), load_state(), db(), now()
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (args.run_id,)).fetchone()
    if not run:
        raise Fail(f"unknown run {args.run_id}")
    rows = conn.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY score DESC", (args.run_id,)).fetchall()
    by = lambda *names: [r for r in rows if r["status"] in names]
    applied, company = by("applied"), by("company_site_queued")
    skipped = by("skipped", "skipped_unknown_question", "skipped_screener", "failed")
    queued = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
    signal = run["signal"] or (state.get("cooldown_signal") if cooldown_until(state, t) else None) or "none"
    out = path("runs") / args.run_id / "report.md"
    final = (f"Applied {len(applied)}/{run['budget']} · queued {queued} · company site {len(company)} · "
             f"signals {signal} · data/runs/{args.run_id}/report.md")

    def questions(r):
        items = json.loads(r["answers"]) if r["answers"] else []
        return "; ".join(a.get("question", "?") + ("*" if str(a.get("source", "")).startswith("derived") else "")
                         for a in items if isinstance(a, dict))

    def reason_kind(r):
        m = re.match(r"prefilter \w+|[a-z]+", (r["reason"] or r["status"]).lower())
        return m[0] if m else r["status"]

    kinds = {}
    for r in skipped:
        kinds[reason_kind(r)] = kinds.get(reason_kind(r), 0) + 1
    scored = [r for r in skipped if r["score"] is not None]
    lines = [f"# Run {args.run_id} ({run['slot']})", "", final, ""]
    if args.notes:
        lines += [pathlib.Path(args.notes).read_text().strip(), ""]
    refused = conn.execute("SELECT job_id, detail FROM events WHERE run_id=? AND kind='rail_refused'", (args.run_id,)).fetchall()
    if refused:
        lines += ["## Refused attempts", *[f"- {r['job_id']}: {r['detail']}" for r in refused], ""]
    lines += ["## Applied", "| Job | Company | Score | Questions (derived answers marked *) |", "|---|---|---|---|"]
    lines += [f"| {r['title']} | {r['company']} | {r['score']} | {questions(r)} |" for r in applied]
    lines += ["", "## Company site", "| Job | Company | Score | Naukri URL |", "|---|---|---|---|"]
    lines += [f"| {r['title']} | {r['company']} | {r['score']} | {r['url']} |" for r in company]
    lines += ["", "## Skipped", ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])) or "None."]
    lines += [f"- {r['score']} {r['title']} ({r['company']}): {r['reason'] or r['status']}"
              for r in (scored if run["dry_run"] else scored[:3])]
    out.write_text("\n".join(lines) + "\n")
    print(final)
    return 0


def cmd_mark(args):
    state, t = load_state(), now()
    if args.what == "refresh":
        state["last_refresh_date"] = t.date().isoformat()
        state["next_variant"] = 2 if args.variant == 1 else 1
    elif args.what == "digest":
        state["last_digest_at"] = stamp(t)
    elif args.what == "weekly":
        state["last_weekly_week"] = f"{t.isocalendar().year}-W{t.isocalendar().week:02d}"
    save_state(state)
    print(f"marked {args.what}")
    return 0


EXPORT_COLUMNS = ("id", "status", "score", "title", "company", "location", "salary", "exp", "posted",
                  "found_via", "keyword_group", "reason", "score_notes", "recruiter_status", "applied_at",
                  "first_seen", "updated_at", "run_id", "url", "company_url", "answers")


def export_csv(conn):
    path("exports").mkdir(parents=True, exist_ok=True)
    out = path("exports") / "jobs.csv"
    rows = conn.execute(f"SELECT {', '.join(EXPORT_COLUMNS)} FROM jobs ORDER BY updated_at DESC").fetchall()
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(EXPORT_COLUMNS)
        w.writerows([tuple(r) for r in rows])
    return out


def cmd_export(args):
    print(f"wrote {export_csv(db())}")
    return 0


def cmd_stats(args):
    conn, t = db(), now()
    if args.run_id:
        rows = conn.execute("SELECT * FROM jobs WHERE run_id=?", (args.run_id,)).fetchall()
        print(f"run {args.run_id} ({len(rows)} jobs)")
    else:
        m = re.fullmatch(r"(\d+)d", args.since)
        since = t - timedelta(days=int(m[1])) if m else datetime.fromisoformat(args.since).replace(tzinfo=IST)
        rows = conn.execute("SELECT * FROM jobs WHERE updated_at >= ?", (stamp(since),)).fetchall()
        print(f"since {since:%Y-%m-%d %H:%M} ({len(rows)} jobs)")

    def tally(items):
        out = {}
        for i in items:
            out[i] = out.get(i, 0) + 1
        return ", ".join(f"{k} {v}" for k, v in sorted(out.items(), key=lambda kv: (-kv[1], str(kv[0])))) or "none"

    applied = [r for r in rows if r["status"] == "applied"]
    bands = lambda s: "<65" if s is None or s < 65 else "65-74" if s < 75 else "75-84" if s < 85 else "85+"
    print("status: " + tally(r["status"] for r in rows))
    print("applied by group: " + tally(r["keyword_group"] or "-" for r in applied))
    print("applied by source: " + tally((r["found_via"] or "-").split(":")[0] for r in applied))
    print("applied by score: " + tally(bands(r["score"]) for r in applied))
    print("recruiter status: " + tally(r["recruiter_status"] for r in rows if r["recruiter_status"]))
    print("skip reasons: " + tally(re.split(r"[:(]", r["reason"] or "-")[0].strip()
                                   for r in rows if r["status"] == "skipped"))
    return 0


# ---------- browser scripts: pack ----------
# Runs retype a script's whole text into javascript_tool (output tokens) and it stays in the
# context afterwards, so runs read scripts/browser/packed/: the same code without comments,
# indentation or blank lines. Strings, templates and regex literals stay byte for byte.

_BEFORE_REGEX = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
                 "case", "do", "else", "yield", "await"}
_WORD = re.compile(r"[A-Za-z_$][\w$]*")
_NUM = re.compile(r"\d[\w.]*|\.\d\w*")


def _skip_string(s, i):
    """Index after the quoted string that starts at i."""
    j = i + 1
    while j < len(s) and s[j] != s[i]:
        j += 2 if s[j] == "\\" else 1
    return j + 1


def _skip_template(s, i):
    """Index after the template literal that starts at i; ${...} may nest strings and templates."""
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
        elif s[j] == "`":
            return j + 1
        elif s.startswith("${", j):
            depth, j = 1, j + 2
            while j < len(s) and depth:
                if s[j] in "'\"":
                    j = _skip_string(s, j)
                elif s[j] == "`":
                    j = _skip_template(s, j)
                else:
                    depth += (s[j] == "{") - (s[j] == "}")
                    j += 1
        else:
            j += 1
    return len(s)


def _skip_regex(s, i):
    """Index after the regex literal (and its flags) that starts at i."""
    j, in_class = i + 1, False
    while j < len(s) and s[j] != "\n":
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "[":
            in_class = True
        elif s[j] == "]":
            in_class = False
        elif s[j] == "/" and not in_class:
            break
        j += 1
    j += 1
    while j < len(s) and s[j].isalpha():
        j += 1
    return j


def js_tokens(s):
    """Yield (kind, text) pairs that rebuild s: ws, nl, comment, string, template, regex, word, num, punct."""
    i, prev = 0, None
    while i < len(s):
        c = s[i]
        if c in " \t\r\f\v":
            j = i
            while j < len(s) and s[j] in " \t\r\f\v":
                j += 1
            kind = "ws"
        elif c == "\n":
            j, kind = i + 1, "nl"
        elif s.startswith("//", i):
            j = s.find("\n", i)
            j, kind = (len(s) if j < 0 else j), "comment"
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            j, kind = (len(s) if j < 0 else j + 2), "comment"
        elif c in "'\"":
            j, kind = _skip_string(s, i), "string"
        elif c == "`":
            j, kind = _skip_template(s, i), "template"
        elif c == "/" and (prev is None or (prev[0] == "punct" and prev[1] not in ")]}")
                           or (prev[0] == "word" and prev[1] in _BEFORE_REGEX)):
            j, kind = _skip_regex(s, i), "regex"
        elif (m := _WORD.match(s, i)):
            j, kind = m.end(), "word"
        elif (m := _NUM.match(s, i)):
            j, kind = m.end(), "num"
        else:
            j, kind = i + 1, "punct"
        yield kind, s[i:j]
        if kind not in ("ws", "nl", "comment"):
            prev = (kind, s[i:j])
        i = j


def pack_js(src):
    """src without comments, indentation or blank lines; a space run becomes one space, a line break stays."""
    out, space, newline = [], False, False
    for kind, text in js_tokens(src):
        if kind == "ws":
            space = True
        elif kind == "nl":
            newline = True
        elif kind == "comment":
            space, newline = True, newline or "\n" in text
        else:
            if out:
                out.append("\n" if newline else " " if space else "")
            out.append(text)
            space = newline = False
    return "".join(out) + "\n" if out else ""


def cmd_pack(args):
    src_dir = root() / "scripts" / "browser"
    out_dir = src_dir / "packed"
    stale, rows = [], []
    for f in sorted(src_dir.glob("*.js")):
        packed = pack_js(f.read_text())
        target = out_dir / f.name
        if not (target.exists() and target.read_text() == packed):
            if args.check:
                stale.append(f.name)
            else:
                out_dir.mkdir(exist_ok=True)
                target.write_text(packed)
        rows.append(f"{f.name}: {f.stat().st_size} -> {len(packed.encode())} bytes")
    if stale:
        print("stale packed scripts: " + ", ".join(stale) + " (run: python3 scripts/jobtool.py pack)")
        return 1
    print("\n".join(rows) if rows else "no scripts in scripts/browser")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="jobtool.py", description="Tracker, prefilter, pacing and run guards.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create data/, the tracker DB and state").set_defaults(fn=cmd_init)
    sub.add_parser("status", help="today's counts, budgets, cooldown, lock (never fails)").set_defaults(fn=cmd_status)

    s = sub.add_parser("start", help="check the guards, take the lock, print budget and searches (exit 3 = blocked)")
    s.add_argument("slot", choices=SLOTS)
    s.add_argument("--dry-run", action="store_true", help="budget 0: score and report, never apply")
    s.add_argument("--force", action="store_true", help="skip the gap-between-runs rule (manual runs); logged")
    s.add_argument("--check", action="store_true", help="run the guards only; take no lock and start no run")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("finish", help="close a run: release the lock, export CSV, cooldown on --signal")
    s.add_argument("run_id")
    s.add_argument("--signal", help="captcha, unusual_activity, blocked, login_page, quota, warning…")
    s.set_defaults(fn=cmd_finish)

    s = sub.add_parser("prefilter", help="dedupe and hard-filter extract_cards.js output; print new jobs to score")
    s.add_argument("--cards", required=True, help="file with the extractor chunks, or - for stdin")
    s.add_argument("--via", help="where the cards came from, e.g. 'search:senior react developer:remote'")
    s.add_argument("--group", help="keyword group of the search")
    s.add_argument("--no-floor", action="store_true", help="skip the pause before the next page load (development)")
    s.set_defaults(fn=cmd_prefilter)

    s = sub.add_parser("score", help='record scores: --json \'[{"id": "…", "score": 80, "why": "…"}]\'')
    s.add_argument("--json", required=True, help="JSON list (or object), or - for stdin")
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("queue", help="queued jobs, best first: id|score|title|company|location|url")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("requeue", help="queue jobs skipped for score at or above --min-score, or (--questions) retry once"
                                       " the jobs abandoned at a question whose answer is now approved")
    s.add_argument("--min-score", type=int)
    s.add_argument("--questions", action="store_true", help="needs [safety] retry_unknown_question = true")
    s.set_defaults(fn=cmd_requeue)

    s = sub.add_parser("update", help="record what happened to one job")
    s.add_argument("id")
    s.add_argument("--status", help=", ".join(STATUSES))
    s.add_argument("--reason")
    s.add_argument("--answers", help="JSON of the screener questions and answers given, or - for stdin")
    s.add_argument("--recruiter-status", dest="recruiter_status")
    s.add_argument("--company-url", dest="company_url")
    s.add_argument("--no-floor", action="store_true", help="skip the pause before the next page load (development)")
    s.add_argument("--override", help="why a refused attempt is recorded anyway, e.g. the owner picked the job; logged")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("pace", help="go | wait <seconds> | stop <reason> for the next application")
    s.add_argument("--wait", action="store_true", help="sleep until the next application is allowed, then print the line")
    s.add_argument("--job", help="also stop unless this job is queued; send before clicking Apply")
    s.set_defaults(fn=cmd_pace)

    s = sub.add_parser("cooldown", help="show, set or clear the cooldown")
    s.add_argument("action", nargs="?", choices=("show", "set", "clear"), default="show")
    s.add_argument("signal", nargs="?")
    s.add_argument("--hours", type=float)
    s.set_defaults(fn=cmd_cooldown)

    sub.add_parser("unlock", help="remove a run lock by hand").set_defaults(fn=cmd_unlock)
    sub.add_parser("reap", help="close a run left open after its process ended (launcher only)").set_defaults(fn=cmd_reap)
    sub.add_parser("backup", help="copy the tracker and private files to data/backups/<date>").set_defaults(fn=cmd_backup)

    s = sub.add_parser("signal", help="start the cooldown now, for a signal seen on a page")
    s.add_argument("name", help=", ".join(COOLDOWN_SIGNALS))
    s.set_defaults(fn=cmd_signal)

    s = sub.add_parser("rescreen", help="jobs the prefilter rejected that today's rules would pass")
    s.add_argument("--apply", action="store_true", help="return them to scoring; prints them like prefilter")
    s.set_defaults(fn=cmd_rescreen)

    s = sub.add_parser("report", help="write the run report from the tracker; prints the final line")
    s.add_argument("run_id")
    s.add_argument("--notes", help="file with the model's sections: Needs you, Refresh and digest")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("mark", help="record that a refresh, digest or weekly report happened")
    s.add_argument("what", choices=("refresh", "digest", "weekly"))
    s.add_argument("--variant", type=int, choices=(1, 2), default=1)
    s.set_defaults(fn=cmd_mark)

    sub.add_parser("export-csv", help="write data/exports/jobs.csv").set_defaults(fn=cmd_export)
    sub.add_parser("audit-answers", help="list screener answers that name no source").set_defaults(fn=cmd_audit_answers)

    s = sub.add_parser("hold", help="on | off | status: while on, `start` is blocked (pause the schedules)")
    s.add_argument("action", nargs="?", choices=("on", "off", "status"), default="status")
    s.set_defaults(fn=cmd_hold)

    s = sub.add_parser("pack", help="write scripts/browser/packed/: the browser scripts without comments or indentation")
    s.add_argument("--check", action="store_true", help="write nothing; exit 1 when a packed copy is missing or stale")
    s.set_defaults(fn=cmd_pack)

    s = sub.add_parser("stats", help="counts by status, group, source, score band and skip reason")
    s.add_argument("--since", default="7d", help="7d or YYYY-MM-DD")
    s.add_argument("--run-id", dest="run_id")
    s.set_defaults(fn=cmd_stats)
    return p


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        return args.fn(args)
    except Fail as e:
        print(str(e))
        return e.code


if __name__ == "__main__":
    sys.exit(main())
