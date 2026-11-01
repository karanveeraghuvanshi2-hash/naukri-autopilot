# Profile edits

Part of `/naukri-setup`, step 5. `knowledge/safety.md` (Profile edits) allows
them only in this session, with the user watching, for the sections the user
approves here. Layout: `knowledge/naukri-ui.md`, Profile. Editor flows
learned so far: `knowledge/forms/naukri-profile-editors.md`.

Order: resume, key skills, headline, desired-job preferences, summary.
Contact, employment, education and personal details stay paste-ready in the
report: the user enters them by hand.

## Proposals

Draft each chosen section from the confirmed files:
- **Resume:** `profile/resume.pdf`.
- **Key skills:** 15–20 skills from the skill table, named as Naukri's
  autosuggest names them, ordered by the target keywords. Alternate spellings
  (ReactJS, React.js) belong in the summary and the resume, so each skill is
  one chip. Show the adds and removals against the current list.
- **Headline:** variant 1 from `profile/answers.md`.
- **Desired-job preferences:** roles, locations, job type and expected salary,
  from `work_mode`, `relocation`, `employment_type` and `expected_ctc`.
- **Summary:** 3–5 sentences with 1–2 measurable results taken from the
  resume, every claim one the resume makes.

Show each section as current → proposed and ask per section: apply as shown,
edit (the user's text, then confirm it), or skip. An approval covers that
section and that exact text only.

## Each approved section

1. Locate the section's edit control with `find` and click it with a real
   click.
2. Read the editor with `find` or `read_page`, scoped to the dialog. When it
   differs from the recorded flow (an AI suggestion, an extra required field,
   an error, an unknown layout): Cancel, hand the section over paste-ready,
   and go to the next section.
3. Enter the approved text with real clicks and typing (`computer`), or
   `form_input` for a plain input or select.
   - **Key skills:** type each skill, wait for the autosuggest, and click the
     matching suggestion. A skill with no matching suggestion goes in the
     report. Remove a chip with its own remove control, one at a time.
   - **Resume:** click the resume section's update control and attach
     `profile/resume.pdf` with `file_upload`. When the upload is rejected or
     no file input is reachable, ask the user to upload it by hand now and
     wait until they say it is done.
   - Upsells and "Improve with AI" or "Add to profile" offers: close or
     ignore them. The text stays exactly as approved.
4. Save, wait 3 s, and run `extract_profile.js`. The section must read
   exactly as approved. When it differs, report what the page shows and hand
   the rest of that section over paste-ready; one attempt per section.
5. Wait 10–20 s before the next section.
6. Record the working flow in `knowledge/forms/naukri-profile-editors.md`:
   controls, selectors and quirks, never values. Set its "Last verified"
   date.

A signal at any point: stop all browser work, run
`python3 scripts/jobtool.py signal <signal>`, and report it.

## After the edits

1. Scroll to the bottom with real scrolls, run `extract_profile.js` with all
   its chunks, and save it as `data/setup/<YYYYMMDD-HHMM>-after.txt`: the
   **after snapshot**.
2. Compare it with the before snapshot. Only the approved sections changed
   (the `hashes:` line), each to the exact approved text. The profile's CTC,
   notice period and locations match `profile/answers.md`. Every difference
   goes in the report; a mismatch in contact or personal details goes there
   paste-ready.
3. After a headline edit, run
   `python3 scripts/jobtool.py mark refresh --variant 1`, so no run edits the
   headline again today.
