# Pending review

`/naukri-setup pending`: clears *Pending review* in `profile/answers.md`. No
browser, and no re-reading of the resume or the Naukri profile.

1. Read `profile/answers.md`, `profile/profile.md` and
   `knowledge/forms/naukri-common-questions.md`.
2. Take the unchecked items oldest first, four per AskUserQuestion call. Show
   each item's question, the answer given (or `?`), the job and how the
   answer was derived. Options:
   - **Approve** (only when an answer was given);
   - **Keep pending**, to decide later;
   - **Delete**: no answer. Jobs that ask it keep being skipped, and the
     question comes back to *Pending review* when a run meets it again;
   - the user's own answer, typed as Other.
3. Write each approved or typed answer to *Approved* as
   `- <pattern> → <answer>`. The pattern is a contiguous run of the
   question's own words that keeps whatever changes the answer (the skill,
   the city, the number of days): `jobtool requeue --questions` matches the
   abandoned jobs' questions by that text. When the answer is a fact that a
   key in `naukri-common-questions.md` covers, record it in *Screener facts*
   too, with its scope.
4. Update `profile/answers.md`: approved items move to *Approved*, deleted
   ones go, kept ones stay.
5. Run `python3 scripts/jobtool.py requeue --questions`. Exit 2 "switched
   off" means retries wait for the smoke test (`knowledge/safety.md`, The
   one retry): say so. Otherwise give the count.
6. Report: approved, typed, deleted, kept, and requeued.
