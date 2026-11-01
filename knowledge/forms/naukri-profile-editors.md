# Form: Naukri profile section editors

How each section editor on `/mnjuser/profile` works, for `/naukri-setup`'s
profile edits (`.claude/skills/naukri-setup/profile-edit.md`). Shareable:
controls, selectors and quirks only, never values. The headline editor is in
`knowledge/naukri-ui.md`, Profile.

Last verified: 2026-10-31.

All editors open a modal and add `?action=modalOpen` to the URL. A saved
section shows a green "Success" banner inside it until the page reloads, which
changes that section's `hashes:` value: reload before an after snapshot. The
first save of a session can raise a Pro upsell modal ("Profile updated
successfully"): close it with its X. "Improve with AI" sits in the headline and
summary editors: ignore it.

## Resume upload

- Do not click "Update resume": it opens the native file picker. `find` "file
  input for resume upload" gives the `#attachCV` input (type file, in
  `.uploadContainer`); pass that ref to `file_upload`.
- There is no confirmation step. The section updates within 3 s.
- Naukri shows the uploaded file's own name. Copy the file to a recognisable
  name first if the name recruiters see matters.

## Key skills

- Open with the button named "Edit key skills". The modal has chips with an X,
  an "Add skills" input, and a suggested set below it.
- Remove chips from the last to the first, so earlier ones keep their position.
  Removing a row of chips moves the input and Save.
- The autosuggest lags behind fast typing and can show matches for the first
  letters only. Type the skill, press Backspace once, wait 2 s, then read the
  list. Multi-word searches can return nothing until shortened further.
- Clear the input with cmd+a and Backspace: repeated Backspace can leave a
  letter behind.
- Clicking a suggestion adds the chip, clears the input and keeps the focus.
  Save sits at the bottom of the modal.

## Desired-job preferences

- Open with the button named "Edit career profile" (`#lazyDesiredProfile`). The
  modal is tall: scroll inside it to reach the location chips, Preferred annual
  salary, Preferred shift (Day, Night, Flexible) and Save.
- The salary input formats digits with Indian commas as you type. cmd+a and
  typing garbles the value. Press End, Backspace until the placeholder shows,
  then type the digits. Read the field before Save.

## Profile summary

- Open with the button named "Edit profile summary". A plain textarea, limit
  1000 characters, counter `.fue__chars-count`, Cancel and Save.
- The modal has a **Delete** link at its top right. Never click it.
- Click the textarea, cmd+a, type. Read the value before Save.
- The saved section truncates at "Read More": click it to verify the full text.
