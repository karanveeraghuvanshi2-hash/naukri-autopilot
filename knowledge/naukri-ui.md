# Naukri UI reference

How naukri.com looks to the agent: URLs, page structure, selectors and texts.
Last verified 2026-10-27 in desktop Chrome, logged in. Naukri changes its UI
often; when something here is wrong, fix this file in the same run and say so
in the run report. Personal values never go in this file (it is shareable).

## Reading pages

- **Extractors.** `scripts/browser/*.js` are read-only. Runs send the packed
  copies in `scripts/browser/packed/` (same code, no comments or indentation).
  Edit a source, then run `python3 scripts/jobtool.py pack`; a test fails
  while a packed copy is stale. Run one by passing the whole file as the
  `text` of `javascript_tool`. Each waits up to 8 s for the
  page to hydrate, then reports `signals` (see `knowledge/safety.md`).
  - `page_signals.js`: any page; returns `{url, title, loggedIn, signals}`.
  - `extract_cards.js`: search results and recommended jobs.
  - `extract_jd.js`: a job page, description included.
  - `extract_profile.js`: the profile page. Line 2 is `hashes:`, one short
    hash per section (`-` while empty), for before/after snapshots; the
    sections' text follows. Unverified on a live page until the first
    `/naukri-setup` run uses it.- **Chunks.** `javascript_tool` cuts every result at 1000 characters, so the
  extractors return `[1/n]` plus the first chunk and keep the rest in the page.
  Fetch chunks 2..n with `next_chunk.js`, all in one `browser_batch` (one item
  per chunk). An empty result means none are left. Navigating clears them.
- **Blocked output.** A result that looks like cookie or query-string data
  (`a=b; c=d`, `?x=y&z=w`) comes back as `[BLOCKED: Cookie/query string data]`.
  The extractors strip `=` and query strings; ad-hoc probes should print with
  `: ` and ` | ` separators.
- **`get_page_text` misreads job pages**: it returns a "similar jobs" card
  instead of the description. Use `extract_jd.js` there. It works on NVites and
  the profile performance page.
- **Classes.** Job pages use CSS modules (`styles_<name>__<hash>`). Match the
  stable part: `[class*="jhc__exp__"]`. The trailing `__` keeps
  `jhc__exp-salary-container__…` out.

## Header (every page)

- Logged in: `.nI-gNb-drawer` and `img.nI-gNb-icon-img` (avatar). On search
  pages the header renders a few seconds after load.
- The Jobs menu (hover "Jobs") lists Recommended jobs, NVites, Application
  status and Saved jobs as scripted items with no links; use the URLs below.
- Login page: `/nlogin/login`.

## URLs

| Page | URL |
|---|---|
| Home | `/mnjuser/homepage` |
| Recommended jobs | `/mnjuser/recommendedjobs` |
| NVites (recruiter invites) | `/mnjuser/inbox` |
| Application status | `/myapply/historypage` |
| Profile performance, recruiter actions | `/mnjuser/performance` |
| Profile | `/mnjuser/profile` |
| Job page | `/job-listings-<slug>-<id>` (id: 12 digits; the slug differs between pages that link the same job, so the id is what counts) |
| Search, anywhere | `/<keyword-slug>-jobs?<params>` |
| Search, one city | `/<keyword-slug>-jobs-in-<city-slug>?<params>` (`[location] search_city`, e.g. `delhi-ncr`) |

## Search results

- **Params (verified):** `wfhType=2` remote, `wfhType=3` hybrid (repeatable;
  office is probably `0`, unverified); `jobAge=1|3|7|15|30` (days since
  posting); `experience=<years>` (keeps jobs whose range includes that value).
  `ctcFilter=25to50` drops every undisclosed-salary job, so don't use salary
  filters. Sort-by-date has no URL param. Pagination is unverified (probably a
  `-2` suffix on the path).
- **Cards:** `div.srp-jobtuple-wrapper[data-job-id]` > `div.cust-job-tuple`:
  `a.title`, `a.comp-name`, `.rating`, `.review`, `.expwdth`, `.sal-wrap`
  (empty when not disclosed), `.locWdth`, `.job-desc`, `li.tag-li` (skills),
  `.job-post-day`. 20 per page; count text "1 - 20 of 94".
- **Relevance is loose.** A "senior frontend developer" city search also returns
  backend, full-stack and L&D roles; the prefilter and scoring do the sorting.
- Open a job by navigating to its URL (one tab), not by clicking the card.

## Recommended jobs

- Tabs: `button.tab-list-item` "Profile (69)", "Preferences (30)", "You might
  like (75)"; the active one has `.tab-list-active`. A tab's cards all load at
  once.
- **Cards:** `article.jobTuple[data-job-id]`: `a.jt-title-link`, `.subTitle`
  (company), `span.typ-12Bold` ("Company rating 3.2"), `.reviewsCount`,
  `li.experience`, `li.salary`, `li.location`, `.job-description`,
  `.jobTupleFooter .fw500` ("4 Days Ago").
- The page offers multi-select ("You can select upto 5 jobs to apply"). Apply
  one job at a time from its job page instead.

## Job page

- **Expired job:** the URL redirects to a search page with `?expJD=true`, which
  reads "Job you are looking for is expired." `extract_jd.js` then prints
  `id: ? | apply: none`, not `apply: closed`, so check the URL before recording
  a failure (seen 2026-11-01).
- **Header:** `h1[class*=jd-header-title]`; company `[class*=jd-header-comp-name]`;
  rating `[class*=jhc__jd-top-head] [class*=amb-rating]` (scope it: the
  similar-jobs cards below carry their own ratings); `[class*="jhc__exp__"]`,
  `[class*="jhc__salary__"]`, `[class*="jhc__wfhmode__"]` (Remote, Hybrid…),
  `[class*="jhc__location__"]`; stats `[class*="jhc__stat__"]` ("Posted: 4 days
  ago", "Openings: 1", "Applicants: 100+").
- **Apply buttons:**
  - `#apply-button` "Apply": applies inside Naukri (rendered twice: header and
    sticky bar). After applying it should read "Applied" (unverified).
  - `#company-site-button` "Apply on company site": a button with no href; it
    opens the employer's site in a new tab.
- **Naukri match score** `[class*=MS__details]`: Early Applicant, Keyskills,
  Location, Work Experience, each with `i.ni-icon-check_circle` (match) or
  `i.ni-icon-crossMatchscore` (miss).
- **Details:** `[class*=other-details] [class*=details]` (Role, Industry Type,
  Department, Employment Type, Role Category); education
  `[class*=education] [class*=details]`; key skills `[class*=key-skill] a.chip`.
- **Description:** `[class*=JDC__dang-inner-html]`.
- A pre-ticked "Follow <company> as you apply" checkbox sits by the Apply
  button. Leave it as Naukri sets it.
- **Apply flow and screening questions:** `knowledge/forms/naukri-screener.md`.

## NVites (`/mnjuser/inbox`)

Jobs recruiters invited the candidate to apply to.

- Filters `div.filter-pills > span.count-pill`: "All (10)", "Unread (3)".
- **Cards:** `div.inbox-company-card` (`.unread`, `.selected`): `span.title`,
  `span.job-location`, `span.experience`, `span.salary`, `span.comp-name`,
  `span.rating-text`, `span.review`, `span.posted-by-txt`, `span.date-time-wrap`
  ("23 Oct"). Cards carry no job link or id.
- Detail pane `section.card-details-container` has `button.not-interested` and
  `button.apply-btn`. Opening a card marks it read.

## Profile performance (`/mnjuser/performance`)

- 90-day totals: `span.summary-card__search-appearance--value`,
  `span.summary-card__recruiter-actions--value`. Also a 7-day search-appearance
  line ("48 Search appearances in last 7 Days", "21% since last week") and an
  activity level (HIGH…).
- **Recruiter actions** `#recruiter-actions-card`: filter tags
  `span.ja-tag-label` + `span.ja-tag-count` (All Actions, Naukri profile
  viewed, Contact viewed, NVite sent…). Each `div.recruiter-card` has
  `.recruiter-info__name`, `.recruiter-info__description` ("<role> at
  <company>"), `.recruiter-info__location`, `span.r-action-name` (the action),
  `span.r-action-time` ("4 days ago"). `span.load-more-button` loads more.
  The cards lazy-load: `get_page_text` misses them until the page is scrolled
  down with real scrolls; then the same read or a short probe sees them. Six
  cards show before "Load more". Past about 6 days the time reads "A week ago".
- Some recruiter cards ask "Did you get a call from this recruiter? Yes / No".
  Leave them unanswered.

## Application status (`/myapply/historypage`)

Counters "Total applies" and "Application updates". With no applications in
90 days it shows "You have not applied to any jobs in last 90 days."

With an application, `get_page_text` returned the selected job's detail view:
title, company, rating, "Application status" with a dated timeline ("Applied",
"Application Sent", "Awaiting Recruiter Action"), "Activity on this job"
counters and the match criteria. Seen 2026-11-01 with one application; the row
list itself is still unrecorded.

## Profile (`/mnjuser/profile`)

- Top card: name, current role, "Profile last updated - 09Oct, 2026".
- **Resume headline** `#lazyResumeHead`: the text after the "Resume headline"
  title. Its edit button is `span.edit.icon` (accessible name "Edit resume
  headline"). The editor modal (URL gains `?action=modalOpen`) has textarea
  `#resumeHeadlineTxt` (maxlength 250, "Minimum 5 words"), counter
  `.fue__chars-count` ("188 character(s) left"), a Cancel link and Save
  `button.btn-dark-ot`.
- Sections: `#lazyKeySkills`, `#lazyEmployment`, `#lazyEducation`,
  `#lazyITSkills`, `#lazyProject`, `#lazyProfileSummary`, `#lazyAccomplishment`,
  `#lazyDesiredProfile`, `#lazyPersonalDetail`. Lazy sections can read empty
  until scrolled into view: scroll to the bottom with real scrolls before a
  full `extract_profile.js` read.
- Section editors other than the headline: see
  `knowledge/forms/naukri-profile-editors.md` (filled in by `/naukri-setup`).

## Upsells and prompts

Naukri Pro, "Neo AI job agent", "Improve with AI", "Become a Pro", "Add to
profile" (fresh details from resume) and "Share interest" (early-access roles)
are outside this tool's scope. Close or ignore them.
