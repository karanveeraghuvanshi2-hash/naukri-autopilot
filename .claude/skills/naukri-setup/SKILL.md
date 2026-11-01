---
name: naukri-setup
description: Onboarding for the Naukri job agent. Drafts the private profile files from the resume and the Naukri profile, confirms the key facts with the user, and edits the Naukri profile sections the user approves while watching. `/naukri-setup pending` reviews Pending review answers only.
disable-model-invocation: true
argument-hint: "[pending]"
allowed-tools:
  - Bash(python3 scripts/jobtool.py status)
  - Bash(python3 scripts/jobtool.py init)
  - Bash(python3 scripts/jobtool.py mark *)
  - Bash(python3 scripts/jobtool.py requeue *)
  - Bash(python3 scripts/jobtool.py signal *)
model: claude-opus-5-5
effort: high
---

# Naukri setup

Arguments: `$ARGUMENTS`. With `pending`, run step 0, then follow `pending.md`
and stop. Otherwise do steps 0–6.

The user started this session and is watching it. Ask with
AskUserQuestion, up to four questions per call.

Setup builds the private files every run reads:

| File | Holds | Template |
|---|---|---|
| `profile/profile.md` | Facts: timeline, skill table, education | `profile.example/profile.example.md` |
| `profile/answers.md` | The answer bank, Screener facts, headline variants | `profile.example/answers.example.md` |
| `profile/preferences.toml` | Experience, targeting, keyword groups, title excludes, caps | `profile.example/preferences.toml` |
| `profile/denylist.txt` | Private terms the leak test keeps out of shareable files | none |

**Truth.** Every value comes from the resume, the Naukri profile or the
user's own words, and the user confirms it before it is written. A draft
marks each value's source: `resume`, `naukri`, `derived` or `?`. Personal
values go only into `profile/` and `data/`. **Re-run:** when a file exists,
keep its confirmed values, fill the empty fields, and change a value only
when the user asks.

## 0. Guard

Run `python3 scripts/jobtool.py status`.
- `lean: no` → stop. Tell the user to quit and start the session with
  `./naukri` from the project folder, which keeps other plugins off while
  private answers are typed, and to run the command again there.
- `lock: held by …` → a run is using Naukri: stop and say when to retry.
- `cooldown: until …` → skip every Naukri page: draft from the resume and the
  existing files, skip step 5, and say so in the report.

## 1. Sources

1. Read `profile/resume.pdf` in full. When it is missing, ask the user to
   save the resume there and stop.
2. Read the existing `profile/` files (a re-run).
3. **Naukri snapshot**, read-only, following `knowledge/safety.md`:
   1. Load the Chrome tools with the ToolSearch call in
      `.claude/skills/naukri-run/SKILL.md` (Preflight), adding
      `mcp__claude-in-chrome__file_upload`. Call `tabs_context_mcp`, then
      open the **setup tab** with `tabs_create_mcp` at
      `https://www.naukri.com/mnjuser/profile`. All browser work happens in
      this tab.
   2. Scroll to the bottom with `computer` scroll actions, a few seconds
      apart, so every lazy section loads.
   3. Run `scripts/browser/packed/extract_profile.js` (the whole file as the
      `text` of `javascript_tool`), then fetch the other chunks with
      `next_chunk.js` in one `browser_batch`. Any signal: stop all browser
      work as `knowledge/safety.md` says for setup.
   4. A section that reads `(empty: …)`: scroll it into view and run the
      extractor once more. Still empty or garbled: read the section with
      `get_page_text`, and note the extractor problem for the report.
   5. Save the whole output as `data/setup/<YYYYMMDD-HHMM>-before.txt`: the
      **before snapshot**.
4. List every mismatch between the resume and the profile (dates, titles,
   skills, experience, CTC, notice period, locations) and every gap between
   jobs.

## 2. Draft

Draft everything from the sources before asking anything:
- **`profile.md`**: summary; timeline, one row per job plus one per gap;
  skill table, where a skill's years count the timeline rows whose resume
  text shows it in use, and a skill is current when the latest job uses it;
  education; skills not claimed.
- **`answers.md`**: Contact, Work, Screener facts and Form-filling
  preferences, as far as the sources state them. The Naukri profile states
  CTC, notice period and locations.
- **Snippets**: the short intro and the cover note.
- **Headline**: two variants, each 5+ words and at most 250 characters, true
  to the resume, carrying the same top keywords. Variant 1 stays close to
  the current headline.
- **`[targeting]`** and search: `target_roles`, `other_roles` (adjacent
  titles worth a lower score), `core_stack`, `avoid_stacks`; three keyword
  groups of 3–6 searches each; title excludes for the stacks and roles
  outside the targeting. Derive them from the timeline, the skill table and
  the headline; the template shows the format.

## 3. Confirm

In this order:
1. **Skills in one line.** Show the skill table (skill, years, current) and
   ask the user for one reply with corrections and a self-rating out of 10
   per skill, written like `React 6y 9, TypeScript 5y 8`. A skill left
   unrated stays unrated.
2. **Explicit confirms**, one AskUserQuestion call, one question each, with
   the sources' value as the first option:
   - current CTC, fixed and variable;
   - notice period, plus the last working day when serving notice;
   - the years of every `core_stack` skill, as one list.

   These three are confirmed here, each on its own, never inside the
   correction in step 6.
3. **Open topics.** Ask about each of these that the sources left open,
   offering the likeliest answers as options:
   - money and time: expected CTC (a figure, or a rule), notice buyout, the
     salary floor in LPA below which a disclosed range is skipped (0 for none);
   - place: remote only, or a city; for a city, the spellings Naukri uses for
     it and its suburbs, and its name in Naukri's search URLs;
   - work: relocation per city, work mode per city, time-zone overlap, work
     authorization, contract or contract-to-hire roles;
   - story: reason for change, one line per gap, and how total experience
     counts (calendar span, or without the gaps);
   - forms: gender, diversity and EEO questions, date of birth, assessments,
     contact details.
4. **Dealbreakers**, one call: consultancy and staffing-firm postings
   (`penalize`, the default; `neutral`; `avoid`), service bonds, shifts
   (night, rotational, UK or US hours), companies to avoid. The first goes
   to `targeting.consultancies`; the rest to `targeting.dealbreakers` and the
   Screener facts `bond` and `shifts`.
5. **Screener facts.** Go through `knowledge/forms/naukri-common-questions.md`
   and ask for each fact the sources and steps 1–4 left open, four per call,
   recording its scope. A time-sensitive fact (`offers_in_hand`) gets
   today's date.
6. **One correction.** Show the whole draft (both files, headline variants,
   intro, cover note, targeting) with each value's source, and ask for every
   remaining correction in one free-text reply. Apply it; ask again only
   about what the reply left unclear.

## 4. Write

1. Write `profile/profile.md` and `profile/answers.md`. Keep *Pending review*
   and *Approved* as they are (empty on a first run).
2. `profile/preferences.toml`: copy the template when it is missing. Set
   `[experience]` (`career_start`, the first full-time job as `YYYY-MM`;
   `gap_months`, when the user counts experience without the gaps),
   `[salary] floor_lpa`, `[location] office` and `search_city` (both empty
   for remote only), `[targeting]`, the keyword groups and the title excludes
   (replace the template's: they suit a frontend engineer). Show the caps and
   run window, and change only what the user asks.
3. `profile/denylist.txt`: one private term per line, lowercase: the full
   name and each part of it longer than two letters, the email and its part
   before `@`, the phone number's last 10 digits, LinkedIn and GitHub
   handles, **every** employer in the timeline, every college, the resume's
   file name on Naukri. Cities, skills and common words stay out: they would
   flag shareable files falsely.
4. Run `python3 scripts/jobtool.py init`, then
   `uv run --with pytest pytest tests/ -q -k private_terms`. A failure lists
   shareable files that hold a private term: put them in the report for a
   development session.

## 5. Profile edits

Ask which Naukri profile sections to edit now (multi-select): resume upload,
key skills, headline, desired-job preferences, summary. Offer the resume
upload when the Naukri resume is older than `profile/resume.pdf` or differs
from it. None chosen → step 6. Otherwise follow `profile-edit.md`.

## 6. Finish

1. Close the setup tab.
2. Report to the user:
   - the files written, and the values the user corrected;
   - each profile section edited, with before → after and the snapshot
     check;
   - **paste-ready** blocks for what the user does by hand: sections handed
     over, and mismatches in contact, employment, education or personal
     details;
   - mismatches left, extractor problems, and the denylist test result;
   - the next step: start a fresh session with `./naukri` and run
     `/naukri-run manual --dry-run`. Setup ends with this report.
