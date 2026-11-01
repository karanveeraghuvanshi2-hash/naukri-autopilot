# Scoring

Part of `/naukri-run`, Apply. Two gates: the **card score** decides who gets
queued, and the **final check** on the job page decides who gets the
application. The sources:
- targeting: `start`'s `targeting.*` lines and the keyword groups in
  `profile/preferences.toml`;
- facts: the skill table and timeline in `profile/profile.md`;
- answers: `relocation`, `work_mode`, `employment_type` and `timezone_overlap`
  in `profile/answers.md`.

A score depends only on the job, never on the budget left.

## Card score

Each new job gets 0–100 from its card line
(`id|title|company|exp|salary|location|posted|rating|tags|dNN`). jobtool
computes `dNN`: the 35 points that need no judgement (experience 15, location
and mode 10, signals 10). You score **role (35) and skills (30)** and pass the
sum as `model` (0–65). jobtool stores `score = model + dNN` and queues jobs at
or above `[scoring] threshold`.

**Role, 35:**

| Points | The title |
|---|---|
| 35 | One of `targeting.target_roles` |
| 20 | One of `targeting.other_roles`, or an AI title whose tags are ML engineering (below) |
| 10 | A target-family title at a junior level |
| 0 | Anything else, or a title that names a stack, platform or domain the table lacks (C#, Data Platform, SoundHound), unless it also says agentic AI or forward deployed |

A consultancy or staffing firm loses 5 when `targeting.consultancies` is
`penalize`, and scores 0 when it is `avoid`. It counts as one when the company
name says staffing, recruitment, manpower, placement, HR services or talent
solutions, or the card says "for our client", "hiring for a client" or "on
behalf of". "Consulting" in a company name doesn't count.

**Skills, 30:**

| Points | The tags |
|---|---|
| 30 | Centre on `targeting.core_stack` or on the table's AI application rows |
| 20 | Those skills plus tags the table lacks |
| 10 | Another framework first with those skills listed, or no tags at all |
| 0 | A stack the table lacks, or one in `targeting.avoid_stacks` |

**AI application or ML engineering.** The table covers AI application work:
LLM APIs, agents, MCP, RAG, vector databases, LangChain, LangGraph, and React
or Python around them. It doesn't cover ML engineering: training or fine-tuning
models, PyTorch, TensorFlow, computer vision, data pipelines, Databricks,
MLOps, GPU serving. "AI Engineer" in a title says nothing either way, so read
the tags. Only tags that name that work count: "Machine learning" or
"Artificial intelligence" alone don't.

Write the `why` as the two parts and a reason: `role 35 · skills 30: React+TS+Next, remote`.
Send `{"id": ..., "model": 65, "why": "..."}`.

## Final check

On the job page, before Apply or `company_site_queued`. Skip with
`jd: <reason>` when the description shows any of:
1. **Main work outside the table:** see below. Also a stack in
   `targeting.avoid_stacks`.
2. **Place:** office or hybrid outside the `[location] office` terms
   in `profile/preferences.toml`, even when the card said remote.
3. **Experience:** a required overall minimum above `experience:` + 1 year.
4. **Salary:** a disclosed maximum below `[salary] floor_lpa`.
5. **Terms:** an employment type outside `employment_type`. Read the body as
   well as the Employment Type field, which often says Full Time on contract
   jobs: "C2C", "C2H", "contract", "project duration", "N months". Also hours
   beyond `timezone_overlap`.
6. **Dealbreaker:** one in `targeting.dealbreakers`.
7. **Match block:** Naukri marks both Work Experience and Location as misses.

Otherwise the card score stands, however low the `keyskills` mark: Naukri marks
it as a miss on most jobs.

**Main work outside the table.** Skip when a skill the table lacks or holds at
0 is one of these:
- named as mandatory, or as must-have, on a primary or core skills list, and
  the job is built on it: a platform such as Amazon Bedrock, SageMaker,
  Databricks, Palantir or Vertex AI, or a language or framework;
- the job's main responsibility, as with ML engineering (above) or a backend
  or API platform whose required skills are server-side, which `Not claimed`
  rules out.

Don't skip for:
- a skill under preferred, nice to have or good to have;
- one skill in a long list, with the core of the job in the table;
- "AWS, Azure or GCP" as a general requirement;
- a job led by `targeting.core_stack`, even with adjacent skills required
  (a full-stack job led by your frontend stack, say);
- a stated years figure for one skill, up to the table's years + 1.

When a job passes with a real gap (a key skill the table lacks, or a skill
years figure above the table's), apply and name it under "Needs you", with the
job, the gap and one line on why it passed.
