# Common screener questions

Questions Naukri screeners ask often, and the fact behind each one.
`/naukri-setup` records each fact **with its scope** under *Screener facts* in
`profile/answers.md`, so a run can answer the variants of a question
truthfully: "Can you join in 30 days?" and "Are you an immediate joiner?"
both come from one notice-period fact. Shareable: patterns only, never values.

**Setup** asks for the facts that the resume, the Naukri profile and the
earlier answers leave open, four per question call. **Runs** read the
*Screener facts* table with the rest of the bank, derive the variant, and log
the source as `bank` (a fact used as written) or `derived: <fact> → <rule>`.
A variant the fact's scope doesn't cover has no honest answer: leave it blank
(`apply.md`, step 4) and add the question to *Pending review*.

Facts already in the Work table (`current_ctc`, `expected_ctc`,
`notice_period`, `relocation`, `work_mode`, `timezone_overlap`,
`work_authorization`, `employment_type`, `reason_for_change`,
`career_gap_note`) are not asked twice; their rows here say how to derive
the variants.

| # | Question pattern | Fact (key) | Scope to record | Derive |
|---|---|---|---|---|
| 1 | Notice period; how soon can you join | `notice_period` | days; serving notice or not; last working day | Pick the nearest option that isn't shorter |
| 2 | Immediate joiner; join within N days | `notice_period`, `buyout` | whether the notice can be bought out or shortened, and to how many days | Yes only when the notice (or the confirmed buyout) fits N |
| 3 | Last working day | `notice_period` | the date, when serving notice | Not serving: say so |
| 4 | Current CTC, fixed, variable | `current_ctc` | fixed and variable split | Convert to the form's unit, yearly or monthly |
| 5 | Expected CTC | `expected_ctc` | a figure, or a rule (e.g. a hike over current) | Apply the rule to the current CTC |
| 6 | Is the CTC negotiable | `ctc_negotiable` | yes / no / within a band | As written |
| 7 | Offers in hand, offered CTC | `offers_in_hand` | count and figures, **as of a date** | Older than 14 days: no honest answer until reconfirmed |
| 8 | Current location | `current_location` | city | As written |
| 9 | Willing to relocate to <city> | `relocation` | per city or region: yes / no | A city outside the list: no honest answer |
| 10 | Office or hybrid in <city>, N days a week | `work_mode` | per city: remote / hybrid (max days) / office | Yes only when the city and days fit |
| 11 | Shifts, night shift, US or UK hours | `shifts`, `timezone_overlap` | which shifts are acceptable; overlap hours | Outside them: a misfit |
| 12 | Work authorization, visa, sponsorship | `work_authorization` | countries; needs sponsorship or not | As written |
| 13 | Valid passport; willing to travel | `passport`, `travel` | yes / no; how much travel | As written |
| 14 | Contract, C2H, freelance, part-time | `employment_type` | each type: yes / no | As written |
| 15 | Service agreement or bond | `bond` | accept or not; the longest acceptable | Longer than that: a misfit |
| 16 | Total experience | (computed) | from `[experience]` | `start`'s `experience:` line, as printed |
| 17 | Years of experience in <skill> | (skill table) | `profile/profile.md` | Round down; no row means 0 |
| 18 | Rate yourself in <skill> | (skill table) | self-rating /10 | No rating: no honest answer |
| 19 | Have you worked with <tool or domain> | (skill table), `domains` | domains worked in (fintech, e-commerce…) | Missing: "No" |
| 20 | Team size led; people managed | `leadership` | direct reports vs mentoring; largest team; since when | Never count mentees as reports |
| 21 | Highest qualification, year, percentage or CGPA | (education), `education_scores` | per degree: score and scale | Convert scales only when the form names one |
| 22 | Full-time or distance degree | (education) | per degree | As written |
| 23 | Gaps in career or education | `career_gap_note` | one line per gap | As written |
| 24 | Reason for leaving or change | `reason_for_change` | one or two sentences | As written |
| 25 | Interviewed or applied here in the last N months | `past_processes` | companies and dates, as known to the user | Not in the list: "No" only when the user confirmed the list is complete |
| 26 | Available for an in-person interview in <city> | `interview_travel` | cities or radius; virtual only | Outside it: no honest answer |
| 27 | Languages known | `languages` | language and level | As written |
| 28 | Laptop and internet for remote work | `remote_setup` | yes / no | As written |
| 29 | LinkedIn, GitHub, portfolio URL | Contact table | URLs | As written |
| 30 | Gender, diversity, disability; date of birth | Form-filling preferences | how to answer each | As written |

Add a row when runs keep sending the same new question to *Pending review*.
