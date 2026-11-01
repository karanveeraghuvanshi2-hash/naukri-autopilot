# Form: Naukri in-platform Apply and screening questions

Applies to jobs whose page shows `#apply-button` "Apply"
(`knowledge/naukri-ui.md`, Job page). Shareable: labels and flow only; the
answers themselves live in `profile/answers.md`.

Last verified: 2026-11-01, one live job (a screener with one question). Record
the real flow here during live applications, then keep it current.

## Closing the screener sends the application

**Seen 2026-11-01:** on a job with one unanswered text question, clicking the
panel's X did not abandon the application. The page went to Apply Confirmation
("Applied to ...") and `/myapply/historypage` showed "Application Sent".

- Runs use this on purpose for a question with no honest answer, by the user's
  choice (`.claude/skills/naukri-run/apply.md`, step 4).
- Unverified: whether X sends on a question without the "Skip this question"
  chip, or partway through a screener with several questions.
- This is a trace of an application, so `[safety] retry_unknown_question` stays
  off (`knowledge/safety.md`, The one retry).

## Flow (to confirm)

1. Final checks done, the job is worth applying to: click `#apply-button`.
2. A job without questions may be submitted by that click alone (reported by
   third parties, unverified). Treat the click as the submission.
3. A job with questions opens a side panel that asks them one at a time
   (third-party reports, unverified).
4. Success: the tab moves to `/myapply/saveApply` (title "Apply Confirmation"),
   which reads `Applied to "<job title>"`. `/myapply/historypage` then lists the
   job with "Application Sent" and "Awaiting Recruiter Action".

The screener seen so far is a right-hand chat-style drawer: the question as a
bubble, a text box with the placeholder "Type message here...", a "Skip this
question" chip, a Save button at the bottom (disabled while empty) and an X at
the top right. `find` locates the question; `read_page` on that ref gives only
the question text, so a screenshot shows the controls.

Questions come one at a time: type the answer, click Save, and the next question
appears lower in the drawer, so take a new screenshot for the box's position.
Saving the last answer submits the application. Seen 2026-11-01 on jobs with 1,
2 and 3 text questions. Some jobs have no screener: Apply submits at once.

A choice question shows checkboxes, one per option, with "Skip this question"
as the last one: click the option's box, then Save (seen 2026-11-01 on a
current-city question). Years questions can also come as radio bands ("No
experience", "<2 years", "2-5 years" and so on): click the band, then Save,
which stays disabled until one is picked. Yes/No questions come as radios the
same way.

After the last Save the drawer shows "Thank you for your response." and the tab
reaches Apply Confirmation a few seconds later, so wait about 5 s before
treating the job as unconfirmed (seen 2026-11-01). The first box and Save keep
the same position while the drawer opens; later controls move down.

## Reading the panel

Read it with `read_page`, using the panel's `ref_id` and a `max_chars` limit.
Never pass `filter: "interactive"` here: it drops the question text, and every
answer depends on reading the exact question.

## Record on the first live applications

- [ ] Panel container, question text, answer controls (chips, radio, text,
      number, dropdown, date) and the Next/Submit/Save buttons, with selectors.
- [ ] Which inputs accept `form_input` and which need real clicks and typing.
- [x] Success text and what `/myapply/historypage` shows after (see Flow).
- [x] Closing the panel mid-way: X sent the application (see the section above).
- [ ] The daily-quota message (third parties quote "Daily quota expired").

## Field map

Label patterns seen on Naukri screeners → key in `profile/answers.md`. Add a
row for every new label. The common questions and their derive rules are in
`naukri-common-questions.md`.

| Label pattern | Answer from | Notes |
|---|---|---|
| notice period / joining time | `notice_period` | |
| current CTC / current salary | `current_ctc` | Same unit the form asks for (LPA vs ₹). |
| expected CTC | `expected_ctc` | |
| current location | `current_location` | |
| relocate / willing to work from <city> | `relocation` | Hybrid/office within the `[location] office` terms is fine; elsewhere, answer from the bank. |
| years of experience in <skill> | `profile.md` skill-years table | No row → 0 or "No" (`apply.md`, Answer rules). |
| total experience | `profile.md` total | |

## Quirks

- The panel's X submits rather than cancels (see the section at the top).
- A text box can cut an answer off: a 146-character answer was saved at about
  100 characters (seen 2026-11-01). Keep free text under 100 characters and
  read the saved bubble after Save.
