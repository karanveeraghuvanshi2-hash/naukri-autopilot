# Recruiter digest

Part of `/naukri-run`, every run. **Read-only:** it reads and scrolls, and the
only click it makes is "load more". Opening an NVite card marks it read, so
cards stay closed. Replies, Apply/Not interested on NVites and "Did you get a
call?" belong to the user. Layouts: `knowledge/naukri-ui.md`.

Runs when `start` printed `digest: due` (or with `--only digest`); on `digest: skip`
it does nothing. Window: since `start`'s `last <time>`, or the last 7 days when
it says `never`.

1. **Recruiter actions.** Navigate to `https://www.naukri.com/mnjuser/performance`
   and run `page_signals.js`. Read the page with `get_page_text`:
   - the 90-day totals, the 7-day search appearances and the activity level;
   - every recruiter card inside the window: name, "role at company",
     location, action and time.

   When every card shown is inside the window, click `span.load-more-button`
   once.
2. **NVites.** Navigate to `https://www.naukri.com/mnjuser/inbox` and read the
   list: the unread count, then title, company, location, experience, salary,
   posted by and date for each card inside the window. Mark the ones that fit
   the targeting. The user can apply to them by hand, since NVites carry no
   job link.
3. **Application status.** Navigate to
   `https://www.naukri.com/myapply/historypage`. Read each application's
   status. When a row matches a tracker job (same title and company), run
   `python3 scripts/jobtool.py update <id> --recruiter-status "<status>"`.
   A job listed here was sent, so `update` corrects a tracker row that said
   otherwise and prints `reconciled`: list those under Application updates.
   Until `knowledge/naukri-ui.md` describes the rows, record their structure
   there the first time rows appear.
4. **Write `data/digest/<YYYY-MM-DD>.md`.** Add one section per run:
   `## <run_id>`, then Highlights (interview, assessment and shortlist news,
   NVites that fit), Recruiter actions, NVites, Application updates, and
   Profile numbers.
5. Run `python3 scripts/jobtool.py mark digest`. Highlights go to the run
   report's "Needs you".
