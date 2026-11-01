# Headline refresh

Part of `/naukri-run`, mornings, when `start` printed
`refresh: due (variant N)`. This is the only profile edit a run makes. The
two approved variants are under "Naukri headline" in `profile/answers.md`.
Layout: `knowledge/naukri-ui.md`, Profile.

1. Navigate the run tab to `https://www.naukri.com/mnjuser/profile` and run
   `extract_profile.js` (it reports signals too). Keep its `hashes:` line:
   the **before snapshot**.
2. Read the current headline: the `## ResumeHead:` line, or the text after
   "Resume headline" in `#lazyResumeHead` when that line is not in the first
   chunk.
3. Choose variant N, or the other variant when the current headline already
   reads exactly like variant N.
4. Click the headline's edit icon (`span.edit.icon`, accessible name "Edit
   resume headline") with a real click.
5. In the editor's textarea (`#resumeHeadlineTxt`), click into the text,
   select all (cmd+a), and type the chosen variant with `computer`'s type
   action. The counter must show characters left.
6. Click Save (`button.btn-dark-ot`) and wait 3 s.
7. Confirm both: the headline section shows the new text, and "Profile last
   updated" shows today's date.
8. Run `extract_profile.js` again: the **after snapshot**. Compare its
   `hashes:` line with the before snapshot. A section other than `ResumeHead`
   that has a hash in both and differs is a change beyond the headline: put
   "Profile changed beyond the headline: <sections>" at the top of the run
   report (`knowledge/safety.md`, Profile edits).
9. Run `python3 scripts/jobtool.py mark refresh --variant <the variant typed>`.

When the editor looks different (an AI suggestion, an extra field, a new
layout), or step 7 fails: click Cancel or close the editor, skip the refresh,
and report what you saw. One attempt per day.
