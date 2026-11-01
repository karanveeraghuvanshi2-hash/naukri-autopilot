# Apply

Part of `/naukri-run`. It uses `start`'s output: run id, budget, `experience:`
and the discovery list. Page layouts and selectors are in
`knowledge/naukri-ui.md`. Pace, caps and signals follow `knowledge/safety.md`.
`update` below is `python3 scripts/jobtool.py update`.

20 and 40 are ceilings. A run that exhausts the pool is a good run: never lower
the bar, retry a keyword or add searches to fill the budget.

## 1. Discover

Each discovery entry is one page load, and the list `start` printed is the
run's whole allowance. Go through it in order: the recommended tabs first on
every run, then each `search <group> <mode> <url>` line.

First run `python3 scripts/jobtool.py rescreen --apply`. Any jobs it prints
passed a rule change since they were rejected: score them with the rest.

For each entry:
1. Load the page:
   - Recommended Profile tab: navigate to
     `https://www.naukri.com/mnjuser/recommendedjobs`.
   - Recommended Preferences tab: on the same page at the top, take a
     screenshot and click the tab by coordinates. A `ref` click can land on the
     footer of a scrolled page and open another site.
   - Search line: navigate to its URL.
2. Run the run's own `data/runs/<run_id>/extract_cards.js`, then fetch chunks
   2..n with `next_chunk.js` in one `browser_batch`. It returns only cards
   worth scoring and counts the rest in its header. Never replace it with a
   shortened probe: `prefilter` refuses output that doesn't add up.
3. Write every chunk, in order, to `data/runs/<run_id>/cards-<k>.txt`, where
   k counts the entries. Send every row the extractor returned, unfiltered.
4. Run `python3 scripts/jobtool.py prefilter --cards data/runs/<run_id>/cards-<k>.txt --via "<source>"`.
   - The source is `recommended:profile`, `recommended:preferences` or
     `search:<keyword>:<mode>`.
   - For a search, add `--group <group>`.
   - Exit 4 means page signals: stop as `knowledge/safety.md` says.
   - Exit 5 means the output doesn't add up. Take one screenshot. "No results
     found" is fine: wait 5 s and go to the next entry. Anything else is a
     broken extractor: name it in the report, and end discovery after two in a
     row.
   - The output lists the new jobs to score.

Discovery ends early when either happens:
- two searches in a row add nothing new; report the thin pool and what was left
  unsearched;
- `start`'s queued count plus the new jobs so far reaches three times the
  budget.

A dry run uses every entry, unless two searches in a row add nothing new.

## 2. Score

Score every new job from its card line with `scoring.md`.
1. Write the scores to `data/runs/<run_id>/scores.json` as
   `[{"id": "…", "model": 0-65, "why": "…"}]`: the role and skills parts only;
   jobtool adds the `dNN` it printed with each job.
2. Run `python3 scripts/jobtool.py score --json - < data/runs/<run_id>/scores.json`.

A dry run ends here.

## 3. Apply loop

`python3 scripts/jobtool.py queue --limit 40` lists queued jobs, best first,
as `id|score|title|company|location|url`. Take only these, in order. Before the
first application, read `knowledge/forms/naukri-screener.md`.

Give every `pace --wait` and every `update` with `--status` a Bash timeout of
300000: `update` sleeps out the pause before the next application, then prints
the pace line. If Bash moves one to the background, wait for it: running it
again or moving on breaks the pacing.

1. **Pace and read, in one message:** run
   `python3 scripts/jobtool.py pace --wait --job <id>`, and alongside it one
   `browser_batch`: navigate the run tab to the job's URL, `extract_jd.js`, and
   three `next_chunk.js` calls. Fetch any further chunks only when they could
   change the decision: stop reading once a skip reason shows.
   `go` means continue. `stop <reason>` ends the loop before any click; the
   reason goes in the report.
2. **Branch** on the header, `page: jd | id: <id> | apply: <kind> | signals: …`:

   | Header shows | Do |
   |---|---|
   | any signal | stop as `knowledge/safety.md` says |
   | `id: ?`, and the tab's URL has `expJD=true` | `update <id> --status skipped --reason "closed"` |
   | `apply: applied` | `update <id> --status skipped --reason "already applied on Naukri"` |
   | `apply: closed` | `update <id> --status skipped --reason "closed"` |
   | `apply: login` | handle it as `login_page` |
   | `apply: none` | `update <id> --status failed --reason "no apply button"` |
   | `apply: company_site` | Final check in `scoring.md`. Pass: `update <id> --status company_site_queued`. Fail: skip as below |
   | `apply: naukri` | Final check in `scoring.md`. Pass: step 3. Fail: `update <id> --status skipped --reason "jd: <why>"` |

3. **Apply.** `find` the header's Apply button, then in one `browser_batch`
   click the first match with a real click, wait 2 s and take a screenshot at
   `scale` 0.5. The button sits twice on the page, so click once.
   - Confirmation (the success text in `naukri-screener.md`, or the button now
     reads "Applied"): go to step 5.
   - A screener: step 4.
   - Anything else: wait 3 s and look again, then
     `update <id> --status failed --reason "<what you saw>"`.
4. **Screener.** Screenshots give the question and the box's position, which
   moves down with each question. For each question in turn:
   1. Find the honest answer (Answer rules below).
   2. No honest answer: never guess. Close the panel with its X: the user chose
      to send the application with the question unanswered (2026-11-01). Log
      the question with answer `(unanswered)` and add it to *Pending review*
      with `?` as the answer.
      - Confirmation appears: go to step 5, and name the question in the
        report's "Needs you".
      - No confirmation: `update <id> --status skipped_unknown_question --reason "<question>"`.
        Next job.
   3. The honest answer shows a misfit: answer it truthfully and go on, so the
      application goes out with the true answer. Name the job and the answer in
      the report's "Needs you". A misfit is a city outside `relocation`, a
      notice period shorter than the user's, hours beyond `timezone_overlap`,
      or an employment type outside `employment_type`. A skill the user lacks
      is answered the same way ("No" or 0).
   4. In one `browser_batch`: click the box or the option, type, click Save,
      wait 3 s, take a screenshot at `scale` 0.5.
   5. Log `{"question": …, "answer": …, "source": "bank" | "derived: <how>"}`,
      with the answer as the saved bubble shows it.

   Saving the last answer submits the application. Allow about 5 s for the
   confirmation, as in step 3.
5. **Record.**
   - After a screener: write the log as a JSON list to
     `data/runs/<run_id>/answers-<id>.json`, then run
     `update <id> --status applied --answers - < data/runs/<run_id>/answers-<id>.json`.
     Without one: `update <id> --status applied`. The output ends with the
     pace line. `REFUSED` means the attempt broke a run rule and nothing was
     recorded: name the job in the report's "Needs you" and end the loop.
   - Add each derived answer to *Pending review* in `profile/answers.md`, once
     per question. Leave it out when the question is already there or in
     *Approved*.
   - Record new screener knowledge in `knowledge/forms/naukri-screener.md`
     during the run: a label, a control, a quirk, the success text. Keep it
     free of personal values and set its "Last verified" date.

The loop ends on the pace line's `stop`, or when the queue is empty.

## Answer rules

Look for an answer in this order:
1. `profile/answers.md`: Approved first, as the user's latest word, then the
   Work table, Screener facts (each within its scope; the derive rules are in
   `knowledge/forms/naukri-common-questions.md`) and Form-filling preferences.
2. Derived from `profile/profile.md`:
   - years in a skill from the skill table, adding the time since its date
     for a current skill;
   - total experience from `start`'s `experience:` line;
   - yes/no from whether the skill table has the skill;
   - education.
3. Nothing: the question has no honest answer. Where the bank says "skip the
   job", read it as this: the application can't be abandoned once the panel is
   open.

The answer must stay true to those sources:
- Numbers as written in the bank. Give CTC in the form's unit (lakhs or
  rupees, yearly or monthly). For notice period, pick the nearest option that
  isn't shorter.
- Skill years round down; total experience stays as `start` prints it. A skill
  missing from the skill table is "No" or 0.
- Free text comes from the bank's snippets, adapted only with facts from
  `profile/profile.md`. Keep it under 100 characters: the box can cut off a
  longer answer.
- A question that claims more than the sources say (a level, a scale, a
  setting) gets no plain "Yes". In a text box, give the source's facts as they
  stand, and add it to *Pending review*. In a choice list, it has no honest
  answer.
- A choice list without a true option leaves the question with no honest
  answer.
