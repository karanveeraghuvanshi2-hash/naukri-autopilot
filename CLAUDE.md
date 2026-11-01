# job-apply

Claude Code skills that apply to jobs on naukri.com for the user. They work in
the user's own logged-in Chrome through Claude in Chrome, and run on a schedule
without anyone watching.

## Rules

1. **Account safety.** The user's Naukri account must never be restricted or
   banned. Before any action on a job portal, read and follow
   `knowledge/safety.md`.
2. **Truthful answers.** Never state a falsehood. Every answer in an
   application comes from the answer bank (`profile/answers.md`) or is derived
   from facts in `profile/profile.md`. When a question has no honest answer,
   leave it unanswered (`apply.md`, step 4) and add it to *Pending review* in
   the answer bank.
3. **Private data lives in `profile/` and `data/`** (gitignored). Skills,
   `knowledge/` and scripts are shareable, so personal values (contact
   details, CTC, dates, employers) stay in those two folders.
4. **The user owns the settings.** Caps and targeting
   (`profile/preferences.toml`), the profile, and the approved answers change
   only when the user asks. Commit only when the user asks.

## Runs

The schedules call `scripts/launchd/run.sh morning|evening` through launchd.
It runs the gates before `claude`, caps spend and time, and alerts on a crash,
then starts `/naukri-run` with the lean settings in
`profile/run-settings.json`; `jobtool start` refuses to run without them. Scheduled runs are unattended, so
questions for the user go in the run report. `/naukri-setup` runs attended,
in a session started with `./naukri`, and is the only place that
edits Naukri profile sections beyond the headline (`knowledge/safety.md`).

During a `/naukri-*` session, the user has switched process skills off: the
skill is the whole method for the session (no brainstorming, planning,
task-observer or review skills).

## Map

| Path | What |
|---|---|
| `naukri` | The launcher people use: starts a lean Chrome session, `schedule`, `unschedule`, `pause`, `resume` |
| `scripts/jobtool.py` | Tracker, prefilter, caps, pacing, lock, cooldown. Run it from the project root as `python3 scripts/jobtool.py <command>`; each command has `--help` |
| `scripts/browser/` | Read-only page extractors. Runs send the packed copies in `packed/` (regenerate with `jobtool pack`) as the `text` of `javascript_tool` |
| `knowledge/naukri-ui.md` | Naukri URLs, selectors and texts |
| `knowledge/forms/` | Form memory: read the matching file before filling a form, update it after |
| `profile/` | Private: resume.pdf, profile.md, preferences.toml, answers.md, run-settings.json, denylist.txt. Templates in `profile.example/`. Anything else private goes in a gitignored `*.local*` file or `docs/` |
| `scripts/evals/` | Replay evals: `harvest.py <run_id>` rebuilds cases in `data/evals/`, `replay.py score\|final\|screener\|all --model <m> --budget <usd>` runs `claude -p` batches and grades them. Run after any change to `scoring.md`, the Answer rules, or the profile |
| `scripts/launchd/` | `run.sh`, the scheduled runs' launcher, and the LaunchAgent template |
| `data/` | Private: tracker.db, state.json, `runs/<run_id>/report.md`, digest/, setup/ (profile snapshots), exports/jobs.csv |

## Development

- Tests: `uv run --with pytest pytest tests/`. jobtool stays stdlib-only and
  changes test-first.
- When Naukri's UI changes, fix `knowledge/naukri-ui.md` and the extractor in
  the same development session, then run `jobtool pack`. A scheduled run fixes
  `knowledge/` only; a broken extractor goes in its report.
- Unattended runs depend on the allow rules in `.claude/settings.json` and the
  matching `allowed-tools` in each skill: `allowed-tools` adds to the allow
  rules, so a broad pattern there undoes a narrow one here. A scheduled run
  starts with `--permission-mode dontAsk`, so a tool or path outside them is
  denied (listed as `permission_denials` in the run's log). Add a rule when a
  skill needs one. The `ask` rules and anything unlisted (`cooldown clear`,
  `hold`, `unlock`, `--force`, `--override`) stay with the user: they prompt in
  an attended session and are denied in a scheduled one.

## Do not try again

A running log, like a researcher's notes, of what failed on this project. When
you make a mistake or an approach fails, add an entry here in the same session,
newest last: the date, what was tried, what happened, and what to do instead.
Read it before starting work. Keep personal values out of it (rule 3).

- **2026-10-31. Chaining a jobtool command** (`jobtool start … ; echo`): denied
  under `dontAsk`, which blocked a scheduled dry run. Run each command alone.
- **2026-11-01. Closing the screener with X to abandon an application:** it sent
  the application instead. Treat X as submit.
- **2026-11-01. Returning long text from `javascript_tool` inside
  `browser_batch`:** output was cut off at about 1,000 characters. Keep each
  result under 900 characters, or store it on `window` and read it in slices.
- **2026-11-01. Writing a run report from memory:** the first draft claimed the
  user had said something they hadn't, and miscounted the pending answers.
  Check each claim and count against the logs before finishing.
- **2026-11-01. Searching more `jobAge=3` keywords to fill the budget:** about
  ten searches kept returning the same 20 to 30 jobs. Stop after two searches
  in a row with nothing new, and report the thin pool.
- **2026-11-01. Compact page probes in place of `extract_cards.js`:** they saved
  tokens, but dropped cards never reached the tracker, which broke dedupe and
  pool counts. Use the run's own extractor; `prefilter` now refuses anything
  else (exit 5).
- **2026-11-01. Applying outside the queue and past the final check on
  judgement:** 7 of the third run's 7 applications broke a written rule and the
  tracker accepted them. Change the rule instead; `update` now refuses
  (`--override` is the user's).
- **2026-11-01. Changing `preferences.toml` and expecting old jobs to follow:**
  rejected rows stay rejected, because `prefilter` treats them as seen. Run
  `jobtool rescreen`.
- **2026-11-01. Refusing a bad attempt only in `update`:** `update` runs after
  the click, so a refusal there can't stop the application and loses its record.
  Rails that must prevent something go before the click (`pace --job`).
- **2026-11-01. Sending `claude -p` stderr into its JSON log:** a stdin warning
  on the first line broke the parse. Redirect stdin from `/dev/null` and keep
  stderr in its own file.
- **2026-11-01. Running `/naukri-run manual` without `caffeinate`:** the Mac
  slept for about 26 minutes during an `update` sleep, which ran past the 300 s
  Bash limit. Run manual sessions under `caffeinate -i`, as `run.sh` does.
- **2026-11-01. Typing a long free-text screener answer:** a 146-character
  answer was saved cut off at about 100. Keep free text under 100 characters.
- **2026-11-01. Treating `apply: none` as a failure:** an expired job redirects
  to a search page with `?expJD=true`. Check the URL first, and record it as
  closed.
