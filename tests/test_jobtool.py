"""Tests for scripts/jobtool.py. Run: uv run --with pytest pytest tests/"""
import csv
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("jobtool", ROOT / "scripts" / "jobtool.py")
jobtool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jobtool)

PREFS = """
[experience]
career_start = "2020-12"

[salary]
floor_lpa = 30

[location]
office = ["delhi", "ncr", "gurgaon", "gurugram", "noida", "ghaziabad", "faridabad"]
search_city = "delhi-ncr"

[titles]
exclude = ["backend", "java", "full stack", "fullstack", ".net", "l&d"]

[[keyword_sets]]
group = "senior-frontend"
keywords = ["senior frontend developer", "senior react developer"]

[[keyword_sets]]
group = "frontend-lead"
keywords = ["frontend lead"]
"""

MORNING = "2026-10-27T10:00:00+05:30"


class Project:
    """A temporary project root driven through jobtool.main()."""

    def __init__(self, root, monkeypatch, capsys):
        self.root = root
        self.monkeypatch = monkeypatch
        self.capsys = capsys
        self.now = MORNING

    def run(self, *args, now=None):
        self.monkeypatch.setenv("JOBTOOL_NOW", now or self.now)
        code = jobtool.main([str(a) for a in args])
        return code, self.capsys.readouterr().out

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Record time.sleep instead of waiting."""
    calls = []
    monkeypatch.setattr(jobtool.time, "sleep", calls.append)
    return calls


@pytest.fixture
def project(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBTOOL_ROOT", str(tmp_path))
    monkeypatch.setenv("NAUKRI_LEAN", "1")
    p = Project(tmp_path, monkeypatch, capsys)
    p.write("profile/preferences.toml", PREFS)
    return p


@pytest.fixture
def ready(project):
    assert project.run("init")[0] == 0
    return project


def card(job_id, title="Senior Frontend Engineer", company="Acme", exp="5-10 Yrs",
         salary="20-35 Lacs PA", location="Remote", tags="React, TypeScript"):
    slug = "senior-frontend-engineer-acme-remote-5-to-10-years"
    return f"{job_id}|{title}|{company}|{exp}|{salary}|{location}|4 Days Ago|3.8|120|{tags}|{slug}"


def cards_file(project, *rows, signals="none", name="cards.txt"):
    text = "[1/1]\n" + f"page: search | total: 94 | count: {len(rows)} | signals: {signals}\n" + "\n".join(rows)
    return project.write(f"data/runs/{name}", text)


# ---------- parsing ----------

@pytest.mark.parametrize("text, want", [
    ("5-10 Yrs", (5, 10)),
    ("5 - 10 years", (5, 10)),
    ("0-1 Yrs", (0, 1)),
    ("10+ Yrs", (10, None)),
    ("", (None, None)),
    ("Not specified", (None, None)),
])
def test_parse_exp(text, want):
    assert jobtool.parse_exp(text) == want


@pytest.mark.parametrize("text, want", [
    ("20-35 Lacs PA", (20.0, 35.0)),
    ("20-35 Lacs P.A.", (20.0, 35.0)),
    ("22.5-27.5 Lacs PA", (22.5, 27.5)),
    ("33 Lacs P.A.", (33.0, 33.0)),
    ("20 - 30 LPA", (20.0, 30.0)),
    ("1-1.5 Cr PA", (100.0, 150.0)),
    ("₹ 25,00,000 - 40,00,000 P.A.", (25.0, 40.0)),
    ("₹ 2,00,000 - 3,00,000 per month", (24.0, 36.0)),
    ("Not disclosed", None),
    ("", None),
    ("$120k - $150k", "non_inr"),
    ("USD 5000-7000 per month", "non_inr"),
])
def test_parse_salary(text, want):
    assert jobtool.parse_salary(text) == want


@pytest.mark.parametrize("text, ok", [
    ("Remote", True),
    ("Hybrid - Gurugram, Chennai, Bengaluru", True),
    ("Delhi / NCR", True),
    ("Noida, Hyderabad, Pune", True),
    ("Temp. WFH - Bengaluru", False),  # temporary WFH: an office in that city later
    ("Work from home", True),
    ("", True),
    ("Bengaluru", False),
    ("Hybrid - Pune, Bengaluru", False),
    ("Abu Dhabi", False),
])
def test_location_ok(text, ok):
    assert jobtool.location_ok(text, jobtool.load_prefs(text=PREFS)) is ok


@pytest.mark.parametrize("title, excluded", [
    ("Senior Frontend Engineer", False),
    ("Senior JavaScript Developer", False),
    ("Senior Backend Engineer", True),
    ("Java Developer", True),
    (".NET Developer", True),
    ("L&D Lead", True),
    ("Fullstack (Python & React)", True),
    ("Full Stack Engineer (Go and React)", True),
])
def test_title_exclusion(title, excluded):
    assert (jobtool.title_excluded(title, jobtool.load_prefs(text=PREFS)) is not None) is excluded


@pytest.mark.parametrize("gap, want", [(0, 5.8), (6, 5.3)])
def test_total_years_counts_from_career_start_minus_gaps(gap, want):
    prefs = jobtool.load_prefs(text=PREFS)
    prefs["experience"]["gap_months"] = gap
    now = datetime.fromisoformat(MORNING)
    assert jobtool.total_years(prefs, now) == want


def test_parse_rows_reads_chunked_extractor_output():
    text = (
        "[1/2]\npage: search | total: 94 | count: 2 | signals: none\n"
        "111111111111|Senior Frontend Engineer|Acme|5-10 Yrs|20-35 Lacs PA|Remote|4 Days Ago|3.8|120|React, TypeScript|senior-frontend-engineer-acme-remote-5-to-10-years\n"
        "[2/2]\n"
        "222222222222|UI Lead|Beta|8-12 Yrs||Noida|1 day ago|||React|/some/other-path\n"
    )
    headers, cards = jobtool.parse_rows(text)
    assert headers == [{"page": "search", "total": "94", "count": "2", "signals": "none"}]
    assert [c["id"] for c in cards] == ["111111111111", "222222222222"]
    assert cards[0]["url"] == "https://www.naukri.com/job-listings-senior-frontend-engineer-acme-remote-5-to-10-years-111111111111"
    assert cards[1]["url"] == "https://www.naukri.com/some/other-path"
    assert cards[0]["tags"] == "React, TypeScript"
    assert cards[1]["salary"] == ""


# ---------- prefilter ----------

@pytest.mark.parametrize("row, reason", [
    (card("100000000001"), None),
    (card("100000000002", salary="Not disclosed"), None),
    (card("100000000003", salary="$120k - $150k"), None),
    (card("100000000004", salary="20-30 Lacs PA"), None),
    (card("100000000005", salary="20-29 Lacs PA"), "salary"),
    (card("100000000006", exp="6-10 Yrs"), None),
    (card("100000000007", exp="2-5 Yrs"), None),
    (card("100000000008", exp="7-12 Yrs"), "experience"),
    (card("100000000009", exp="3-4 Yrs"), "experience"),
    (card("100000000010", location="Bengaluru"), "location"),
    (card("100000000011", title="Senior Backend Engineer"), "title"),
])
def test_prefilter_rules(row, reason):
    prefs = jobtool.load_prefs(text=PREFS)
    _, cards = jobtool.parse_rows(row)
    got = jobtool.reject_reason(cards[0], prefs, total=5.8)
    assert (got.split(":")[0] if got else None) == reason


def test_prefilter_records_rejects_and_reports_survivors(ready):
    f = cards_file(ready,
                   card("100000000001"),
                   card("100000000002", salary="20-29 Lacs PA"),
                   card("100000000003", location="Bengaluru"),
                   card("100000000001"))
    code, out = ready.run("prefilter", "--cards", f, "--via", "search:senior react developer:remote")
    assert code == 0
    first, *survivors = out.strip().splitlines()
    assert first.startswith("new 1 | seen 1 | rejected 2")
    assert [s.split("|")[0] for s in survivors] == ["100000000001"]

    code, out = ready.run("prefilter", "--cards", f)
    assert out.startswith("new 0 | seen 4 | rejected 0")


def test_prefilter_stops_on_page_signals(ready):
    f = cards_file(ready, card("100000000001"), signals="captcha")
    code, out = ready.run("prefilter", "--cards", f)
    assert code == 4
    assert "captcha" in out
    code, out = ready.run("prefilter", "--cards", cards_file(ready, card("100000000001"), name="ok.txt"))
    assert out.startswith("new 1")


def test_prefilter_requires_init(project):
    f = cards_file(project, card("100000000001"))
    code, out = project.run("prefilter", "--cards", f)
    assert code == 2
    assert "init" in out


# ---------- scoring and queue ----------

def test_score_queues_at_threshold_and_skips_below(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001"), card("100000000002"), card("100000000003")))
    scores = [{"id": "100000000001", "score": 80, "why": "React, remote"},
              {"id": "100000000002", "score": 65, "why": "lead role"},
              {"id": "100000000003", "score": 64, "why": "Angular heavy"}]
    code, out = ready.run("score", "--json", json.dumps(scores))
    assert code == 0
    assert out.startswith("queued 2 | skipped 1")
    code, out = ready.run("queue")
    lines = out.strip().splitlines()
    assert [l.split("|")[0] for l in lines] == ["100000000001", "100000000002"]
    assert lines[0].endswith("https://www.naukri.com/job-listings-senior-frontend-engineer-acme-remote-5-to-10-years-100000000001")


def test_score_rejects_unknown_job(ready):
    code, out = ready.run("score", "--json", json.dumps([{"id": "999999999999", "score": 90}]))
    assert code == 2
    assert "999999999999" in out


def test_queue_drops_stale_jobs(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))
    ready.run("score", "--json", json.dumps([{"id": "100000000001", "score": 80}]))
    later = (datetime.fromisoformat(MORNING) + timedelta(days=8)).isoformat()
    code, out = ready.run("queue", now=later)
    assert out.strip() == ""


def test_requeue_restores_scores_at_or_above_new_threshold(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001"), card("100000000002")))
    ready.run("score", "--json", json.dumps([{"id": "100000000001", "score": 60}, {"id": "100000000002", "score": 50}]))
    code, out = ready.run("requeue", "--min-score", "60")
    assert out.startswith("requeued 1")
    assert [l.split("|")[0] for l in ready.run("queue")[1].strip().splitlines()] == ["100000000001"]


# ---------- run guards ----------

def test_start_blocks_outside_window(ready):
    code, out = ready.run("start", "morning", now="2026-10-27T07:30:00+05:30")
    assert code == 3
    assert "window" in out


def test_start_takes_lock_and_reports_budget(ready):
    code, out = ready.run("start", "morning")
    assert code == 0
    assert "budget: 13" in out
    code, out = ready.run("start", "evening")
    assert code == 3
    assert "lock" in out


def test_start_reports_total_experience(ready):
    code, out = ready.run("start", "morning")
    assert "experience: 5.8 yrs" in out


def test_finish_releases_lock_but_recent_run_blocks_catch_up(ready):
    code, out = ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    assert ready.run("finish", run_id)[0] == 0
    code, out = ready.run("start", "evening", now="2026-10-27T12:00:00+05:30")
    assert code == 3
    assert "recent" in out
    code, out = ready.run("start", "evening", "--force", now="2026-10-27T12:00:00+05:30")
    assert code == 0


def test_stale_lock_is_replaced(ready):
    ready.run("start", "morning")
    code, out = ready.run("start", "evening", now="2026-10-27T18:30:00+05:30")
    assert code == 0
    assert "stale" in out


def test_signal_starts_24h_cooldown(ready):
    ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    ready.run("finish", run_id, "--signal", "captcha")
    code, out = ready.run("start", "morning", now="2026-10-28T09:30:00+05:30")
    assert code == 3
    assert "cooldown" in out
    code, out = ready.run("start", "morning", now="2026-10-28T10:30:00+05:30")
    assert code == 0


def test_cooldown_clear_lifts_it(ready):
    ready.run("cooldown", "set", "unusual_activity")
    assert ready.run("start", "morning", now="2026-10-27T15:00:00+05:30")[0] == 3
    ready.run("cooldown", "clear")
    assert ready.run("start", "morning", now="2026-10-27T15:00:00+05:30")[0] == 0


def test_start_rotates_keyword_sets_across_runs(ready):
    code, out = ready.run("start", "morning")
    assert "https://www.naukri.com/senior-frontend-developer-jobs?wfhType=2&jobAge=3&experience=6" in out
    assert "https://www.naukri.com/senior-frontend-developer-jobs-in-delhi-ncr?jobAge=3&experience=6" in out
    assert "frontend-lead" not in out
    ready.run("finish", jobtool.current_run_id())
    code, out = ready.run("start", "evening", now="2026-10-27T18:30:00+05:30")
    assert "https://www.naukri.com/frontend-lead-jobs?wfhType=2&jobAge=3&experience=6" in out
    assert "senior-frontend-developer" not in out


def test_refresh_due_once_a_day_and_alternates_variants(ready):
    code, out = ready.run("start", "morning")
    assert "refresh: due (variant 1)" in out
    ready.run("mark", "refresh", "--variant", "1")
    ready.run("finish", jobtool.current_run_id())
    code, out = ready.run("start", "morning", now="2026-10-28T09:30:00+05:30")
    assert "refresh: due (variant 2)" in out
    ready.run("mark", "refresh", "--variant", "2", now="2026-10-28T09:40:00+05:30")
    ready.run("finish", jobtool.current_run_id(), now="2026-10-28T10:00:00+05:30")
    code, out = ready.run("start", "morning", now="2026-10-28T14:00:00+05:30")
    assert code == 0
    assert "refresh: due" not in out


# ---------- applying, pacing and caps ----------

def queue_jobs(project, n):
    ids = [f"2000000000{i:02d}" for i in range(n)]
    project.run("prefilter", "--cards", cards_file(project, *[card(i) for i in ids], name=f"q{n}.txt"))
    project.run("score", "--json", json.dumps([{"id": i, "score": 80} for i in ids]))
    return ids


def test_pace_waits_60_to_120_seconds_after_an_application(ready):
    ids = queue_jobs(ready, 2)
    ready.run("start", "morning")
    assert ready.run("pace")[1].split()[0] == "go"
    code, out = ready.run("update", ids[0], "--status", "applied")
    assert code == 0
    word, seconds = ready.run("pace")[1].split()[:2]
    assert word == "wait"
    assert 60 <= int(seconds) <= 120
    later = (datetime.fromisoformat(MORNING) + timedelta(seconds=121)).isoformat()
    assert ready.run("pace", now=later)[1].split()[0] == "go"


def test_pace_wait_sleeps_until_the_gap_ends_then_says_go(ready, monkeypatch):
    ids = queue_jobs(ready, 2)
    ready.run("start", "morning")
    ready.run("update", ids[0], "--status", "applied")
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        later = datetime.fromisoformat(os.environ["JOBTOOL_NOW"]) + timedelta(seconds=seconds)
        monkeypatch.setenv("JOBTOOL_NOW", later.isoformat())

    monkeypatch.setattr(time, "sleep", fake_sleep)
    code, out = ready.run("pace", "--wait")
    assert code == 0
    assert len(slept) == 1 and 60 <= slept[0] <= 120
    assert out.split()[0] == "go"


def test_pace_wait_returns_stop_at_once(ready, monkeypatch):
    queue_jobs(ready, 1)
    ready.run("start", "morning", "--dry-run")
    monkeypatch.setattr(time, "sleep", lambda s: pytest.fail("slept although pace says stop"))
    code, out = ready.run("pace", "--wait")
    assert code == 0
    assert out.startswith("stop")


def test_pace_stops_when_run_budget_is_used(ready):
    ready.write("profile/preferences.toml", PREFS + "\n[caps]\nper_run = 2\n")
    ids = queue_jobs(ready, 3)
    ready.run("start", "morning")
    for i in ids[:2]:
        ready.run("update", i, "--status", "applied")
    out = ready.run("pace")[1]
    assert out.startswith("stop")
    assert "run budget" in out


def test_evening_budget_is_what_the_day_has_left(ready):
    ready.write("profile/preferences.toml", PREFS + "\n[caps]\nper_day = 5\nper_run = 3\nevening_max = 4\n")
    ids = queue_jobs(ready, 3)
    ready.run("start", "morning")
    for i in ids:
        ready.run("update", i, "--status", "applied")
    ready.run("finish", jobtool.current_run_id())
    code, out = ready.run("start", "evening", now="2026-10-27T18:30:00+05:30")
    assert "budget: 2" in out


def test_two_consecutive_failures_stop_the_run(ready):
    ids = queue_jobs(ready, 3)
    ready.run("start", "morning")
    ready.run("update", ids[0], "--status", "failed", "--reason", "screener did not load")
    assert ready.run("pace")[1].startswith("wait")  # a failed attempt is paced like a submission
    ready.run("update", ids[1], "--status", "failed", "--reason", "screener did not load")
    out = ready.run("pace")[1]
    assert out.startswith("stop")
    assert "failures" in out


def test_closing_a_screener_is_paced_like_a_submission(ready):
    ids = queue_jobs(ready, 2)
    ready.run("start", "morning")
    code, out = ready.run("update", ids[0], "--status", "skipped_screener", "--reason", "fit: relocate to Pune -> No")
    assert code == 0
    assert ready.run("pace")[1].startswith("wait")


def test_dry_run_has_no_budget(ready):
    queue_jobs(ready, 1)
    code, out = ready.run("start", "morning", "--dry-run")
    assert "budget: 0" in out
    assert ready.run("pace")[1].startswith("stop")


def test_update_rejects_unknown_status_and_protects_applied_jobs(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning")
    assert ready.run("update", ids[0], "--status", "done")[0] == 2
    ready.run("update", ids[0], "--status", "applied", "--answers", json.dumps({"Notice period": "15 days"}))
    code, out = ready.run("update", ids[0], "--status", "skipped")
    assert code == 2
    assert "applied" in out
    assert ready.run("update", ids[0], "--recruiter-status", "viewed")[0] == 0


def test_update_rejects_bad_answers_json(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning")
    assert ready.run("update", ids[0], "--status", "applied", "--answers", "{not json")[0] == 2


def test_update_reads_answers_json_from_stdin(ready, monkeypatch):
    ids = queue_jobs(ready, 1)
    answers = {"Why are you looking for a change?": "I'd like to own a product's frontend"}
    ready.run("start", "morning")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(answers)))
    code, out = ready.run("update", ids[0], "--status", "applied", "--answers", "-")
    assert code == 0
    saved = jobtool.db().execute("SELECT answers FROM jobs WHERE id=?", (ids[0],)).fetchone()[0]
    assert json.loads(saved) == answers


def test_applied_job_leaves_the_queue(ready):
    ids = queue_jobs(ready, 2)
    ready.run("update", ids[0], "--status", "applied", "--override", "test setup")
    assert [l.split("|")[0] for l in ready.run("queue")[1].strip().splitlines()] == [ids[1]]


# ---------- status, export, stats ----------

def test_status_before_init_does_not_fail(project):
    code, out = project.run("status")
    assert code == 0
    assert "not initialized" in out


def test_status_prints_lean_first_even_without_files(project, monkeypatch):
    jobtool.path("prefs").unlink()  # a first /naukri-setup: no tracker, no preferences yet
    assert project.run("status")[1].splitlines()[0] == "lean: yes"
    project.run("init")
    out = project.run("status")[1]
    assert out.splitlines()[0] == "lean: yes" and "jobtool status error" in out  # no preferences.toml
    monkeypatch.delenv("NAUKRI_LEAN")
    assert project.run("status")[1].splitlines()[0] == "lean: no"


def test_status_shows_today_and_pending_answers(ready):
    ready.write("profile/answers.md", "# Answers\n\n## Pending review\n- [ ] q1\n- [x] q2\n- [ ] q3\n\n## Approved\n- [ ] not pending\n")
    ids = queue_jobs(ready, 1)
    ready.run("update", ids[0], "--status", "applied", "--override", "test setup")
    code, out = ready.run("status")
    assert "applied today: 1/25" in out
    assert "pending answers: 2" in out


def test_export_csv_writes_every_job(ready):
    ids = queue_jobs(ready, 2)
    ready.run("update", ids[0], "--status", "applied", "--override", "test setup")
    assert ready.run("export-csv")[0] == 0
    with open(ready.root / "data" / "exports" / "jobs.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert {r["id"]: r["status"] for r in rows} == {ids[0]: "applied", ids[1]: "queued"}


def test_stats_counts_statuses_since(ready):
    ids = queue_jobs(ready, 3)
    ready.run("update", ids[0], "--status", "applied", "--override", "test setup")
    ready.run("update", ids[1], "--status", "company_site_queued")
    code, out = ready.run("stats", "--since", "7d")
    assert code == 0
    assert re.search(r"(?<![\w])applied 1\b", out)
    assert re.search(r"(?<![\w])company_site_queued 1\b", out)
    assert re.search(r"(?<![\w])queued 1\b", out)


def test_large_keyword_set_resumes_where_its_last_turn_stopped(ready):
    ready.write("profile/preferences.toml", PREFS.replace(
        'keywords = ["senior frontend developer", "senior react developer"]',
        'keywords = ["k one", "k two", "k three"]') + "\n[search]\nmax_pages = 4\n")
    slots = [("morning", "2026-10-27T09:00:00+05:30"), ("evening", "2026-10-27T13:00:00+05:30"),
             ("evening", "2026-10-27T17:00:00+05:30")]
    outs = []
    for slot, at in slots:
        code, out = ready.run("start", slot, now=at)
        assert code == 0
        outs.append(out)
        ready.run("finish", jobtool.current_run_id(), now=at)
    first, third = outs[0], outs[2]
    assert "/k-one-jobs?" in first and "/k-two-jobs-in-delhi-ncr?" in first and "/k-three-" not in first
    assert "/k-three-jobs?" in third and "/k-three-jobs-in-delhi-ncr?" in third


def test_weekly_report_due_on_sunday_evening_once(ready):
    sunday = "2026-11-01T18:30:00+05:30"
    code, out = ready.run("start", "evening", now=sunday)
    assert "weekly: due" in out
    ready.run("mark", "weekly", now=sunday)
    ready.run("finish", jobtool.current_run_id(), now=sunday)
    code, out = ready.run("start", "evening", "--force", now="2026-11-01T19:00:00+05:30")
    assert "weekly: due" not in out


def test_a_success_resets_the_failure_count(ready):
    ids = queue_jobs(ready, 3)
    ready.run("start", "morning")
    ready.run("update", ids[0], "--status", "failed")
    ready.run("update", ids[1], "--status", "applied")
    ready.run("update", ids[2], "--status", "failed")
    assert ready.run("pace")[1].startswith("wait")


def test_score_refuses_applied_jobs(ready):
    ids = queue_jobs(ready, 1)
    ready.run("update", ids[0], "--status", "applied", "--override", "test setup")
    code, out = ready.run("score", "--json", json.dumps([{"id": ids[0], "score": 10}]))
    assert code == 2
    assert ready.run("stats", "--since", "7d")[1].count("applied 1") >= 1


# ---------- pack: browser scripts without comments or indentation ----------

BROWSER = ROOT / "scripts" / "browser"
REAL_SCRIPTS = sorted(BROWSER.glob("*.js"))


def significant(js):
    """Tokens that matter to the interpreter: no whitespace, no comments."""
    return [t for t in jobtool.js_tokens(js) if t[0] not in ("ws", "nl", "comment")]


def test_pack_strips_comments_indentation_and_blank_lines():
    src = "// header\nconst a = 1;  // trailing\n\n  /* block\n  comment */\n  if (a) {\n    b();\n  }\n"
    assert jobtool.pack_js(src) == "const a = 1;\nif (a) {\nb();\n}\n"


def test_pack_keeps_strings_templates_and_regex_literals_intact():
    src = (
        "const u = 'http://x//y';\n"
        'const q = "a // b /* c */";\n'
        "const t = `x // ${a /* k */ + `n`}   y`;\n"
        "const r = /ab+\\/c[/]d/g;\n"
    )
    assert jobtool.pack_js(src) == src


def test_pack_tells_division_from_regex():
    src = "const d = a / b / c;\nconst e = x.split(/ +/).map(s => s / 2);\nreturn /x/.test(y);\n"
    assert jobtool.pack_js(src) == src


def test_pack_collapses_space_runs_and_keeps_line_breaks():
    assert jobtool.pack_js("return   await   foo (  x ,   y )\n") == "return await foo ( x , y )\n"
    assert jobtool.pack_js("a\n   ++b  \n") == "a\n++b\n"  # a line break can end a statement: keep it


def test_pack_is_idempotent():
    src = "// c\nconst a = `${1}`;   /* x */ const b = /r/g; // t\n\n\n  a / b;\n"
    once = jobtool.pack_js(src)
    assert jobtool.pack_js(once) == once


@pytest.mark.parametrize("script", REAL_SCRIPTS, ids=lambda p: p.name)
def test_packed_scripts_are_current_and_keep_every_token(script):
    packed = BROWSER / "packed" / script.name
    assert packed.exists(), f"run: python3 scripts/jobtool.py pack ({script.name} has no packed copy)"
    source = script.read_text()
    assert packed.read_text() == jobtool.pack_js(source), f"stale: run python3 scripts/jobtool.py pack ({script.name})"
    assert significant(packed.read_text()) == significant(source)
    assert len(packed.read_text()) < len(source)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("script", REAL_SCRIPTS, ids=lambda p: p.name)
def test_packed_scripts_are_valid_javascript(script, tmp_path):
    out = tmp_path / "check.mjs"  # the scripts use top-level await: check them as a module
    out.write_text(jobtool.pack_js(script.read_text()))
    done = subprocess.run(["node", "--check", str(out)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_pack_command_writes_packed_copies_and_check_finds_stale_ones(project):
    src = project.write("scripts/browser/a.js", "// note\nconst a = 1;  // x\n")
    code, out = project.run("pack")
    assert code == 0 and "a.js" in out
    packed = project.root / "scripts" / "browser" / "packed" / "a.js"
    assert packed.read_text() == "const a = 1;\n"
    assert project.run("pack", "--check")[0] == 0
    src.write_text("// note\nconst a = 2;\n")
    code, out = project.run("pack", "--check")
    assert code == 1 and "a.js" in out


# ---------- lean launcher guard and hold ----------

def test_start_needs_the_lean_launcher(ready, monkeypatch):
    monkeypatch.delenv("NAUKRI_LEAN")
    code, out = ready.run("start", "manual")
    assert code == 3 and "NAUKRI_LEAN" in out
    assert "lean: no" in ready.run("status")[1]


def test_status_shows_lean_and_hold(ready):
    out = ready.run("status")[1]
    assert "lean: yes" in out and "hold: off" in out


def test_hold_blocks_start_until_it_is_released(ready):
    assert ready.run("hold", "on")[0] == 0
    code, out = ready.run("start", "manual")
    assert code == 3 and "hold" in out
    assert "hold: on" in ready.run("status")[1]
    assert ready.run("hold", "off")[0] == 0
    assert ready.run("start", "manual")[0] == 0


# ---------- targeting ----------

TARGETING = """
[targeting]
target_roles = "senior frontend or React engineer; frontend lead"
core_stack = "React, TypeScript"
avoid_stacks = "Angular-only"
"""


def test_start_prints_the_targeting_section(project):
    project.write("profile/preferences.toml", PREFS + TARGETING)
    project.run("init")
    out = project.run("start", "manual")[1]
    assert "targeting.target_roles: senior frontend or React engineer; frontend lead" in out
    assert "targeting.core_stack: React, TypeScript" in out
    assert "targeting.consultancies: penalize" in out
    assert "targeting.other_roles" not in out  # empty keys stay out


def test_start_prints_the_dealbreakers(project):
    assert jobtool.DEFAULTS["targeting"]["dealbreakers"] == ""
    project.write("profile/preferences.toml", PREFS + TARGETING + 'dealbreakers = "service bonds; night shifts"\n')
    project.run("init")
    out = project.run("start", "manual")[1]
    assert "targeting.dealbreakers: service bonds; night shifts" in out


# ---------- deterministic points ----------

def job_card(**kw):
    base = {"exp": "5-10 Yrs", "salary": "20-35 Lacs PA", "location": "Remote", "posted": "4 Days Ago", "rating": "3.8"}
    return {**base, **kw}


@pytest.mark.parametrize("field, value, want", [
    ("exp", "5-10 Yrs", 15), ("exp", "3-6 Yrs", 15), ("exp", "6-10 Yrs", 8), ("exp", "2-5 Yrs", 8),
    ("exp", "8+ Yrs", 0), ("exp", "2-4 Yrs", 0), ("exp", "", 8),
])
def test_det_experience_points(field, value, want):
    prefs = jobtool.load_prefs(text=PREFS)
    assert jobtool.det_points(job_card(**{field: value}), prefs, 5.8)["exp"] == want


@pytest.mark.parametrize("location, want", [
    ("Remote", 10), ("Remote, Bengaluru", 10), ("Work from home", 10),
    ("Hybrid - Delhi / NCR, Hyderabad", 8), ("Noida", 6), ("Temp. WFH - Gurgaon", 6), ("", 5),
])
def test_det_location_points(location, want):
    prefs = jobtool.load_prefs(text=PREFS)
    assert jobtool.det_points(job_card(location=location), prefs, 5.8)["loc"] == want


@pytest.mark.parametrize("fields, want", [
    ({}, 6),                                                         # rating 2 + freshness 1 + salary 3
    ({"rating": "4.2", "posted": "Today", "salary": "40-50 Lacs PA"}, 10),
    ({"rating": "", "posted": "Just now", "salary": ""}, 6),         # hidden values: neutral points
    ({"rating": "3.2", "posted": "30+ Days Ago", "salary": "Not disclosed"}, 2),
    ({"posted": "1 Day Ago"}, 8),
    ({"posted": "7 Days Ago"}, 6),
    ({"posted": "8 Days Ago"}, 5),
])
def test_det_signal_points(fields, want):
    prefs = jobtool.load_prefs(text=PREFS)
    assert jobtool.det_points(job_card(**fields), prefs, 5.8)["sig"] == want


def test_prefilter_prints_det_points_and_score_adds_the_model_part(ready):
    out = ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))[1]
    assert out.strip().splitlines()[1].endswith("|d31")  # exp 15 + loc 10 + sig 6
    code, out = ready.run("score", "--json", json.dumps([{"id": "100000000001", "model": 50, "why": "role 35 · skills 15"}]))
    assert code == 0 and out.startswith("queued 1")
    row = ready.run("queue")[1].strip().split("|")
    assert row[0] == "100000000001" and row[1] == "81"
    notes = sqlite3.connect(ready.root / "data" / "tracker.db").execute("select score_notes from jobs").fetchone()[0]
    assert "role 35 · skills 15" in notes and "det 31" in notes


def test_score_rejects_a_model_part_above_65(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))
    code, out = ready.run("score", "--json", json.dumps([{"id": "100000000001", "model": 66}]))
    assert code == 2 and "65" in out


# ---------- reposts ----------

def test_prefilter_skips_a_repost_of_a_recent_job(ready):
    f = cards_file(ready, card("100000000001"), card("100000000002", title="Senior  Frontend Engineer!"))
    out = ready.run("prefilter", "--cards", f)[1]
    assert out.startswith("new 1 | seen 0 | rejected 1: repost 1")
    later = (datetime.fromisoformat(MORNING) + timedelta(days=31)).isoformat()
    assert ready.run("prefilter", "--cards", cards_file(ready, card("100000000003"), name="b.txt"), now=later)[1].startswith("new 1")


def test_a_job_rejected_by_the_prefilter_does_not_make_a_later_posting_a_repost(ready):
    f = cards_file(ready, card("100000000001", location="Bengaluru"), card("100000000002"))
    assert ready.run("prefilter", "--cards", f)[1].startswith("new 1 | seen 0 | rejected 1: location 1")


# ---------- digest due ----------

@pytest.mark.parametrize("slot, now, last, word", [
    ("evening", "2026-10-27T19:00:00+05:30", "2026-10-26T22:00:00+05:30", "due"),   # 21 h
    ("evening", "2026-10-27T19:00:00+05:30", "2026-10-27T14:00:00+05:30", "skip"),  # 5 h
    ("morning", "2026-10-27T09:30:00+05:30", "2026-10-26T19:30:00+05:30", "skip"),  # 14 h: yesterday's evening digest
    ("morning", "2026-10-27T09:30:00+05:30", "2026-10-26T08:30:00+05:30", "due"),   # 25 h: catch up
    ("evening", "2026-10-27T19:00:00+05:30", None, "due"),
])
def test_start_says_whether_the_digest_is_due(ready, slot, now, last, word):
    state = json.loads((ready.root / "data" / "state.json").read_text())
    if last:
        state["last_digest_at"] = last
    (ready.root / "data" / "state.json").write_text(json.dumps(state))
    out = ready.run("start", slot, "--force", now=now)[1]
    assert f"digest: {word} | last {last or 'never'}" in out


# ---------- page-load floor and final-check skips ----------

def active_run_with_jobs(ready, n=1, dry=False):
    ready.run("start", "manual", *(["--dry-run"] if dry else []))
    ready.run("prefilter", "--cards", cards_file(ready, *[card(f"10000000000{i}", company=f"Acme {i}") for i in range(1, n + 1)]))


def test_update_sleeps_out_the_page_load_floor(ready, sleeps):
    active_run_with_jobs(ready)
    sleeps.clear()
    ready.run("update", "100000000001", "--status", "skipped", "--reason", "closed")
    assert len(sleeps) == 1 and 10 <= sleeps[0] <= 20


def test_floor_can_be_skipped_and_never_applies_without_a_run(ready, sleeps):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))
    ready.run("update", "100000000001", "--status", "skipped", "--reason", "x")
    assert sleeps == []
    active_run_with_jobs(ready, 2)
    sleeps.clear()
    ready.run("update", "100000000002", "--status", "skipped", "--reason", "x", "--no-floor")
    assert sleeps == []


def test_prefilter_sleeps_the_floor_between_search_pages(ready, sleeps):
    ready.run("start", "manual", "--dry-run")
    sleeps.clear()
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))
    assert len(sleeps) == 1 and 10 <= sleeps[0] <= 20


def test_five_final_check_skips_in_a_row_stop_the_run(ready):
    active_run_with_jobs(ready, 6)
    for i in range(1, 5):
        ready.run("update", f"10000000000{i}", "--status", "skipped", "--reason", "jd: Angular only")
        assert ready.run("pace")[1].startswith("go")
    ready.run("update", "100000000005", "--status", "skipped", "--reason", "jd: onsite")
    assert ready.run("pace")[1].startswith("stop 5 final-check skips in a row")


def test_an_application_resets_the_final_check_skip_count(ready):
    active_run_with_jobs(ready, 6)
    for i in range(1, 5):
        ready.run("update", f"10000000000{i}", "--status", "skipped", "--reason", "jd: Angular only")
    ready.run("update", "100000000005", "--status", "applied")
    ready.run("update", "100000000006", "--status", "skipped", "--reason", "jd: Angular only")
    assert not ready.run("pace")[1].startswith("stop 5")


# ---------- answer audit and retry by question ----------

def test_audit_answers_lists_answers_without_a_source(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001")))
    answers = [{"question": "Notice period?", "answer": "15 days", "source": "bank"},
               {"question": "Years of Redux?", "answer": "5", "source": "derived: skill table"},
               {"question": "Rate your React", "answer": "9"},
               {"question": "Do you have a pet?", "answer": "No", "source": "guess"}]
    ready.run("update", "100000000001", "--status", "applied", "--override", "test setup", "--answers", json.dumps(answers))
    code, out = ready.run("audit-answers")
    assert code == 0
    assert "Rate your React" in out and "Do you have a pet?" in out
    assert "Notice period?" not in out and "Years of Redux?" not in out
    assert "unsourced answers: 2" in out


def abandon_at_question(p, job_id, question):
    p.run("prefilter", "--cards", cards_file(p, card(job_id, company=f"Co {job_id}"), name=f"{job_id}.txt"))
    p.run("update", job_id, "--status", "skipped_unknown_question", "--override", "test setup", "--reason", question)


APPROVED = "## Pending review\n\n## Approved\n\n- do you have a valid passport → Yes\n"


def test_retry_by_question_is_switched_off_by_default(ready):
    ready.write("profile/answers.md", APPROVED)
    abandon_at_question(ready, "100000000001", "Do you have a valid passport?")
    code, out = ready.run("requeue", "--questions")
    assert code == 2 and "retry_unknown_question" in out


def test_retry_by_question_requeues_once_and_only_for_approved_questions(project):
    project.write("profile/preferences.toml", PREFS + "\n[safety]\nretry_unknown_question = true\n")
    project.run("init")
    project.write("profile/answers.md", APPROVED)
    abandon_at_question(project, "100000000001", "Do you have a valid passport?")
    abandon_at_question(project, "100000000002", "Are you comfortable with night shifts?")
    assert project.run("requeue", "--questions")[1].startswith("requeued 1")
    assert [l.split("|")[0] for l in project.run("queue")[1].strip().splitlines()] == ["100000000001"]
    # it hits an unknown question again: the retry is spent
    project.run("update", "100000000001", "--status", "skipped_unknown_question", "--override", "test setup", "--reason", "Do you have a valid passport?")
    assert project.run("requeue", "--questions")[1].startswith("requeued 0")


# ---------- shareable files hold no private terms ----------

SHAREABLE = ["CLAUDE.md", "README.md", "LICENSE", "naukri", ".gitignore", "docs/assets", "knowledge", ".claude/skills",
             ".claude/settings.json", "profile.example", "scripts", "tests"]


def shareable_files():
    for entry in SHAREABLE:
        p = ROOT / entry
        yield from ([p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file()))


@pytest.mark.skipif(not (ROOT / "profile" / "denylist.txt").exists(), reason="no profile/denylist.txt")
def test_shareable_files_hold_no_private_terms():
    terms = [t.strip().lower() for t in (ROOT / "profile" / "denylist.txt").read_text().splitlines() if t.strip()]
    hits = []
    for f in shareable_files():
        if f.suffix in (".pyc", ".db", ".pdf") or "__pycache__" in f.parts:
            continue
        # The repo's own GitHub URL names its owner, and is public by definition.
        text = re.sub(r"github\.com/[^/\s]+/naukri-autopilot", "", f.read_text(errors="ignore").lower())
        hits += [f"{f.relative_to(ROOT)}: {t!r}" for t in terms if jobtool._has_term(text, t)]
    assert not hits, "private terms in shareable files:\n" + "\n".join(hits)


# ---------- rails inside a run ----------

def test_update_refuses_an_attempt_outside_a_run(ready):
    ids = queue_jobs(ready, 1)
    code, out = ready.run("update", ids[0], "--status", "applied")
    assert code == 2
    assert "REFUSED" in out
    assert jobtool.db().execute("SELECT status FROM jobs WHERE id=?", (ids[0],)).fetchone()[0] == "queued"


def test_update_refuses_an_attempt_in_a_dry_run(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning", "--dry-run")
    assert ready.run("update", ids[0], "--status", "applied")[0] == 2


def test_update_refuses_a_job_that_is_not_queued_and_stops_the_run(ready):
    ready.run("start", "morning")
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001", title="Backend Engineer")))
    code, out = ready.run("update", "100000000001", "--status", "applied")
    assert code == 2
    assert "not queued" in out
    assert ready.run("pace")[1].startswith("stop attempt refused")
    kinds = [r[0] for r in jobtool.db().execute("SELECT kind FROM events")]
    assert "rail_refused" in kinds


def test_update_refuses_past_the_run_budget(ready):
    ready.write("profile/preferences.toml", PREFS + "\n[caps]\nper_run = 1\n")
    ids = queue_jobs(ready, 2)
    ready.run("start", "morning")
    assert ready.run("update", ids[0], "--status", "applied")[0] == 0
    code, out = ready.run("update", ids[1], "--status", "applied")
    assert code == 2
    assert "run budget" in out


def test_update_refuses_to_apply_twice(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning")
    ready.run("update", ids[0], "--status", "applied")
    assert ready.run("update", ids[0], "--status", "applied")[0] == 2


def test_override_records_an_attempt_and_logs_why(ready):
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001", title="Backend Engineer")))
    code, out = ready.run("update", "100000000001", "--status", "applied", "--override", "owner picked it")
    assert code == 0
    row = jobtool.db().execute("SELECT detail FROM events WHERE kind='override'").fetchone()
    assert "owner picked it" in row[0]


def test_a_refused_attempt_is_cleared_by_the_next_run(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning")
    ready.run("update", "100000000099", "--status", "applied")  # unknown: no rail state
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001", title="Backend Engineer")), now=MORNING)
    ready.run("update", "100000000001", "--status", "applied")
    ready.run("finish", jobtool.current_run_id())
    ready.run("start", "evening", now="2026-10-27T18:30:00+05:30")
    assert ready.run("pace", now="2026-10-27T18:31:00+05:30")[1].startswith("go")


def test_status_changes_that_are_not_attempts_need_no_run(ready):
    ids = queue_jobs(ready, 1)
    assert ready.run("update", ids[0], "--status", "skipped", "--reason", "x")[0] == 0


def test_update_sleeps_out_the_application_gap_even_with_no_floor(ready, sleeps):
    ids = queue_jobs(ready, 2)
    ready.run("start", "morning")
    sleeps.clear()
    ready.run("update", ids[0], "--status", "applied", "--no-floor")
    assert len(sleeps) == 1 and 60 <= sleeps[0] <= 120


def test_pace_job_refuses_a_job_outside_the_queue(ready):
    ids = queue_jobs(ready, 1)
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001", title="Backend Engineer"), name="b.txt"))
    ready.run("start", "morning")
    assert ready.run("pace", "--job", ids[0])[1].startswith("go")
    out = ready.run("pace", "--job", "100000000001")[1]
    assert out.startswith("stop job 100000000001")
    assert ready.run("pace", "--job", "999999999999")[1].startswith("stop job 999999999999")


# ---------- signals set the cooldown themselves ----------

def test_prefilter_signal_starts_the_cooldown_with_no_finish(ready):
    f = cards_file(ready, card("100000000001"), signals="captcha")
    assert ready.run("prefilter", "--cards", f)[0] == 4
    code, out = ready.run("start", "morning", now="2026-10-27T15:00:00+05:30")
    assert code == 3
    assert "cooldown" in out


def test_prefilter_login_signal_starts_no_cooldown(ready):
    f = cards_file(ready, card("100000000001"), signals="login_page")
    assert ready.run("prefilter", "--cards", f)[0] == 4
    assert "no cooldown" in ready.run("cooldown")[1]


def test_signal_command_starts_the_cooldown(ready):
    code, out = ready.run("signal", "unusual_activity")
    assert code == 0
    assert ready.run("start", "morning", now="2026-10-27T15:00:00+05:30")[0] == 3


def test_signal_command_rejects_a_name_with_no_cooldown(ready):
    assert ready.run("signal", "login_page")[0] == 2


def test_finish_keeps_a_cooldown_already_running(ready):
    ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    ready.run("signal", "captcha")
    until = jobtool.load_state()["cooldown_until"]
    ready.run("finish", run_id, "--signal", "captcha", now="2026-10-27T11:00:00+05:30")
    assert jobtool.load_state()["cooldown_until"] == until


# ---------- gap, force, lock, corrupt files ----------

def test_a_dry_run_does_not_count_toward_the_gap(ready):
    ready.run("start", "manual", "--dry-run")
    ready.run("finish", jobtool.current_run_id())
    assert ready.run("start", "morning", now="2026-10-27T11:00:00+05:30")[0] == 0


def test_force_past_the_gap_is_logged(ready):
    ready.run("start", "morning")
    ready.run("finish", jobtool.current_run_id())
    ready.run("start", "evening", "--force", now="2026-10-27T12:00:00+05:30")
    assert jobtool.db().execute("SELECT COUNT(*) FROM events WHERE kind='force'").fetchone()[0] == 1


def test_lock_is_taken_atomically(ready, monkeypatch):
    real = jobtool.os.open

    def lose_the_race(file, flags, *a):
        if str(file).endswith("run.lock"):
            assert flags & os.O_EXCL
            raise FileExistsError(file)
        return real(file, flags, *a)

    monkeypatch.setattr(jobtool.os, "open", lose_the_race)
    code, out = ready.run("start", "morning")
    assert code == 3
    assert "lock" in out
    assert jobtool.db().execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_corrupt_lock_blocks_start_and_unlock_clears_it(ready):
    ready.write("data/run.lock", "{half")
    code, out = ready.run("start", "morning")
    assert code == 3
    assert "unlock" in out
    assert ready.run("unlock")[0] == 0
    assert ready.run("start", "morning")[0] == 0


def test_corrupt_state_blocks_start(ready):
    ready.write("data/state.json", "{half")
    code, out = ready.run("start", "morning")
    assert code == 3
    assert "state.json" in out


def test_start_check_runs_the_gates_and_takes_nothing(ready):
    code, out = ready.run("start", "morning", "--check")
    assert code == 0
    assert not (ready.root / "data" / "run.lock").exists()
    assert jobtool.db().execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert "rotation" not in jobtool.load_state()
    ready.run("hold", "on")
    assert ready.run("start", "morning", "--check")[0] == 3


def test_reap_closes_a_run_left_open(ready):
    assert ready.run("reap")[1].strip() == "clean"
    ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    code, out = ready.run("reap")
    assert code == 0
    assert out.startswith(f"reaped {run_id}")
    assert not (ready.root / "data" / "run.lock").exists()
    conn = jobtool.db()
    assert conn.execute("SELECT finished_at FROM runs").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM events WHERE kind='run_crashed'").fetchone()[0] == 1


# ---------- discovery ----------

@pytest.mark.parametrize("slot", ["morning", "evening", "manual"])
def test_every_slot_reads_recommended(ready, slot):
    ready.write("profile/preferences.toml", PREFS + "\n[search]\nmax_pages = 3\n")
    code, out = ready.run("start", slot)
    assert "recommended tabs Profile, Preferences" in out


def test_evening_recommended_stays_inside_the_page_allowance(ready):
    ready.write("profile/preferences.toml", PREFS.replace('["frontend lead"]', '["frontend lead", "ui lead", "web lead", "react lead", "next lead"]').replace(
        '[[keyword_sets]]\ngroup = "senior-frontend"\nkeywords = ["senior frontend developer", "senior react developer"]\n\n', '')
        + "\n[search]\nmax_pages = 6\n")
    code, out = ready.run("start", "evening")
    assert "max 6 page loads" in out
    assert len(re.findall(r"^search ", out, re.M)) == 4


def test_prefilter_fails_loudly_on_an_unknown_page(ready):
    f = ready.write("data/runs/u.txt", "[1/1]\npage: unknown | total: ? | count: 0 | signals: none\n")
    code, out = ready.run("prefilter", "--cards", f)
    assert code == 5
    assert "unknown" in out


def test_prefilter_fails_loudly_on_no_header(ready):
    f = ready.write("data/runs/n.txt", card("100000000001"))
    assert ready.run("prefilter", "--cards", f)[0] == 5
    assert jobtool.db().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_prefilter_fails_loudly_when_rows_go_missing(ready):
    f = ready.write("data/runs/m.txt", "page: search | total: 9 | count: 3 | signals: none\n" + card("100000000001"))
    code, out = ready.run("prefilter", "--cards", f)
    assert code == 5
    assert "3" in out and "1" in out
    assert jobtool.db().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_prefilter_reports_what_the_page_filtered(ready):
    f = ready.write("data/runs/f.txt", "page: search | total: 9 | count: 1 | seen: 4 | excluded: 7 | signals: none\n" + card("100000000001"))
    code, out = ready.run("prefilter", "--cards", f)
    assert code == 0
    assert "seen 4" in out and "page-excluded 7" in out


def test_start_writes_a_run_extractor_with_the_rules(ready):
    ready.write("scripts/browser/packed/extract_cards.js", shutil_source())
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001"), card("100000000002", title="Backend Engineer")))
    ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    text = (ready.root / "data" / "runs" / run_id / "extract_cards.js").read_text()
    assert "100000000001" in text
    assert "100000000002" not in text  # the title rule drops it anyway
    assert "backend" in text


def shutil_source():
    return (ROOT / "scripts" / "browser" / "packed" / "extract_cards.js").read_text()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_title_rule_matches_jobtool():
    prefs = jobtool.load_prefs(text=PREFS.replace('".net", "l&d"', '".net", "l&d", "c++", "ai/ml"'))
    titles = ["Senior .NET Developer", "L&D Manager", "Full Stack Engineer", "Frontend Engineer", "Backendish Dev",
              "C++ Developer", "AI/ML Lead", "Java", "JavaScript Developer", "fullstack dev", "Internet Lead"]
    pattern = jobtool.title_pattern(prefs)
    script = f"const rx=new RegExp({json.dumps(pattern)},'i');console.log(JSON.stringify({json.dumps(titles)}.map(t=>rx.test(t))))"
    got = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert got == [jobtool.title_excluded(t, prefs) is not None for t in titles]


# ---------- rescreen, reconcile, report, backup ----------

def stranded(ready):
    ready.write("profile/preferences.toml", PREFS)
    ready.run("prefilter", "--cards", cards_file(ready, card("100000000001", title="Full Stack Engineer"), card("100000000002", title="Java Engineer")))
    ready.write("profile/preferences.toml", PREFS.replace('"full stack", ', ""))


def test_rescreen_lists_rows_a_rule_change_would_free(ready):
    stranded(ready)
    code, out = ready.run("rescreen")
    assert code == 0
    assert "would free 1" in out
    assert jobtool.db().execute("SELECT status FROM jobs WHERE id='100000000001'").fetchone()[0] == "skipped"


def test_rescreen_apply_returns_rows_to_scoring(ready):
    stranded(ready)
    code, out = ready.run("rescreen", "--apply")
    assert "100000000001|Full Stack Engineer" in out
    conn = jobtool.db()
    row = conn.execute("SELECT status, reason, det FROM jobs WHERE id='100000000001'").fetchone()
    assert row["status"] == "new" and row["reason"] is None and row["det"] is not None
    assert conn.execute("SELECT status FROM jobs WHERE id='100000000002'").fetchone()[0] == "skipped"


def test_rescreen_leaves_old_rows_alone(ready):
    stranded(ready)
    code, out = ready.run("rescreen", now="2026-11-20T10:00:00+05:30")
    assert "would free 0" in out


def test_recruiter_status_proves_an_application_was_sent(ready):
    ids = queue_jobs(ready, 1)
    ready.run("start", "morning")
    ready.run("update", ids[0], "--status", "failed", "--reason", "no confirmation")
    code, out = ready.run("update", ids[0], "--recruiter-status", "Application Sent")
    assert code == 0
    assert "reconciled" in out
    row = jobtool.db().execute("SELECT status, applied_at FROM jobs WHERE id=?", (ids[0],)).fetchone()
    assert row["status"] == "applied" and row["applied_at"]


def test_report_renders_counts_from_the_tracker_with_the_notes(ready):
    ids = queue_jobs(ready, 3)
    ready.run("start", "morning")
    run_id = jobtool.current_run_id()
    answers = json.dumps([{"question": "Notice?", "answer": "15", "source": "bank"},
                          {"question": "Figma?", "answer": "0", "source": "derived: table"}])
    ready.run("update", ids[0], "--status", "applied", "--answers", answers)
    ready.run("update", ids[1], "--status", "company_site_queued")
    ready.run("update", ids[2], "--status", "skipped", "--reason", "jd: Angular only")
    notes = ready.write(f"data/runs/{run_id}/notes.md", "## Needs you\nNothing.\n")
    code, out = ready.run("report", run_id, "--notes", notes)
    assert code == 0
    assert out.startswith(f"Applied 1/13 ")
    text = (ready.root / "data" / "runs" / run_id / "report.md").read_text()
    assert "## Needs you\nNothing." in text
    assert "Figma?*" in text and "Notice?*" not in text
    assert "jd 1" in text


def test_finish_backs_up_the_private_files_and_keeps_14(ready):
    ready.write("profile/answers.md", "# bank\n")
    backups = ready.root / "data" / "backups"
    for i in range(1, 20):
        (backups / f"202601{i:02d}").mkdir(parents=True)
    ready.run("start", "morning")
    ready.run("finish", jobtool.current_run_id())
    today = backups / "20261027"
    assert (today / "tracker.db").exists() and (today / "answers.md").exists() and (today / "preferences.toml").exists()
    assert sqlite3.connect(today / "tracker.db").execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert len(list(backups.iterdir())) == 14


# ---------- launcher ----------

LAUNCHER = ROOT / "scripts" / "launchd" / "run.sh"


def launcher_env(tmp_path, claude_body):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    stubs = {"claude": claude_body, "osascript": f'echo "notify $*" >> "{calls}"', "pgrep": "exit 0",
             "open": f'echo "open $*" >> "{calls}"'}
    for name, body in stubs.items():
        f = bin_dir / name
        f.write_text(f"#!/bin/bash\n{body}\n")
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "JOBTOOL_ROOT": str(tmp_path),
           "JOBTOOL_NOW": MORNING, "NAUKRI_CHROME_WAIT": "0", "NAUKRI_RUN_TIMEOUT": "2"}
    return env, calls


@pytest.fixture
def launch_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JOBTOOL_ROOT", str(tmp_path))
    monkeypatch.setenv("NAUKRI_LEAN", "1")
    p = Project(tmp_path, monkeypatch, capsys)
    p.write("profile/preferences.toml", PREFS)
    p.run("init")
    return p


def launch(tmp_path, env):
    return subprocess.run(["bash", str(LAUNCHER), "morning"], env=env, capture_output=True, text=True, timeout=30)


def test_launcher_never_starts_claude_when_blocked(launch_root, tmp_path):
    launch_root.run("hold", "on")
    env, calls = launcher_env(tmp_path, f'echo claude >> "{tmp_path}/calls.log"')
    assert launch(tmp_path, env).returncode == 0
    assert not calls.exists() or "claude" not in calls.read_text()
    blocked = list((tmp_path / "data" / "runs").glob("*-morning-blocked.md"))
    assert blocked and "hold" in blocked[0].read_text()


def test_launcher_passes_the_spend_cap_and_logs_the_result(launch_root, tmp_path):
    body = f"""echo "$*" >> "{tmp_path}/args.log"
echo "Warning: no stdin data received" >&2
echo '{{"total_cost_usd": 1.5, "permission_denials": [{{"tool_name": "Bash"}}]}}'"""
    env, calls = launcher_env(tmp_path, body)
    assert launch(tmp_path, env).returncode == 0
    args = (tmp_path / "args.log").read_text()
    assert "/naukri-run morning" in args and "--max-budget-usd" in args and "dontAsk" in args
    assert "cost 1.5 denials 1" in (tmp_path / "data" / "logs" / "runs.log").read_text()
    assert "denied" in calls.read_text()


def test_launcher_reaps_and_alerts_on_a_crash(launch_root, tmp_path):
    body = 'python3 scripts/jobtool.py start morning > /dev/null; exit 1'
    env, calls = launcher_env(tmp_path, body)
    env["NAUKRI_LEAN"] = "1"
    assert launch(tmp_path, env).returncode == 1
    assert not (tmp_path / "data" / "run.lock").exists()
    assert "notify" in calls.read_text()


def test_launcher_kills_a_run_past_the_timeout(launch_root, tmp_path):
    env, calls = launcher_env(tmp_path, "exec sleep 20")
    env["NAUKRI_RUN_TIMEOUT"] = "1"
    started = time.time()
    assert launch(tmp_path, env).returncode != 0
    assert time.time() - started < 10
    assert "notify" in calls.read_text()


# ---------- location is the user's, not the code's ----------

ONE_GROUP = '[[keyword_sets]]\ngroup = "g"\nkeywords = ["react developer"]\n'


def search_urls(prefs):
    return [url for _, _, url in jobtool.next_searches(prefs, {}, 8.0, 10)]


def test_search_uses_the_configured_city():
    prefs = jobtool.load_prefs(text='[location]\noffice = ["bengaluru", "bangalore"]\nsearch_city = "bengaluru"\n' + ONE_GROUP)
    urls = search_urls(prefs)
    assert any("/react-developer-jobs-in-bengaluru?" in u for u in urls)
    assert not any("delhi" in u for u in urls)
    assert jobtool.location_ok("Bengaluru", prefs) and not jobtool.location_ok("Noida", prefs)


def test_no_city_searches_remote_only():
    prefs = jobtool.load_prefs(text=ONE_GROUP)
    urls = search_urls(prefs)
    assert len(urls) == 1 and "wfhType=2" in urls[0]
    assert jobtool.location_ok("Remote", prefs) and not jobtool.location_ok("Noida", prefs)


def test_older_ncr_key_keeps_working():
    prefs = jobtool.load_prefs(text='[location]\nncr = ["noida"]\n' + ONE_GROUP)
    assert any("-jobs-in-delhi-ncr?" in u for u in search_urls(prefs))
    assert jobtool.location_ok("Noida", prefs)
