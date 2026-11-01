# Answer bank

The single source for every answer a form gets. `/naukri-setup` copies this
template to `profile/answers.md` (private) and fills it with the user. Field
maps in `knowledge/forms/` point at the `keys` below. Facts such as dates,
skills and years live in `profile/profile.md`; answers derived from them are
logged under *Pending review*.

## Contact

| Key | Answer |
|---|---|
| `full_name` | |
| `email` | |
| `phone` | |
| `current_location` | City, state |
| `linkedin` | |
| `portfolio` | GitHub or site |

## Work

| Key | Answer | Notes |
|---|---|---|
| `notice_period` | | e.g. "15 days"; pick the closest option a form offers, never a shorter one |
| `current_ctc` | | fixed + variable in LPA; convert to the unit the form asks |
| `expected_ctc` | | a figure, or how to answer when a number is required |
| `relocation` | | where the user would move or commute to, and where not |
| `work_mode` | | remote / hybrid / office, and where each is acceptable |
| `timezone_overlap` | | hours the user can overlap with foreign teams |
| `work_authorization` | | e.g. citizen of …, sponsorship needed or not |
| `employment_type` | | full-time; whether contract or contract-to-hire roles are welcome |
| `reason_for_change` | | one or two sentences |
| `career_gap_note` | | one sentence per gap |

## Screener facts

Facts with their scope, behind the common screener questions in
`knowledge/forms/naukri-common-questions.md` (the key column matches its
fact keys). A run derives each question's variants from these.

| Key | Fact | Scope / as of |
|---|---|---|

## Form-filling preferences

How to answer recurring question types.

| Question type | Answer |
|---|---|
| How did you hear about us | Naukri (or the portal the job came from) |
| Gender, diversity, disability, EEO | Prefer not to say, where the form offers it |
| Date of birth | |
| Willing to take an assessment / test | |
| Self-rating of a skill (1–10) | The rating in the profile's skill table; no row means skip the job |
| Earliest joining date | Today plus `notice_period` |

## Snippets

### Short intro

Two or three sentences for "tell us about yourself" boxes.

### Cover note

A template with `{company}` and `{role}` placeholders, used only when a form
requires one.

## Naukri headline

Two approved variants that the morning refresh alternates between (5+ words,
at most 250 characters).

1.
2.

## Pending review

Answers the agent derived or could not give, newest last. The user edits each
one, then moves it to *Approved* or deletes it.
Format: `- [ ] YYYY-MM-DD · <question> → <answer, or ? when none> · <job id, company> · <how it was derived>`

## Approved

Reusable answers the user confirmed, one per line:
`- <question, as a pattern> → <answer>`
