#!/usr/bin/env python3
"""Rebuild eval inputs in data/evals/ from session transcripts and the tracker.

Job text and answers stay in data/ (private). Stdlib only.
Usage: python3 scripts/evals/harvest.py <run_id> [transcript_dir]
"""
import glob
import json
import os
import re
import sqlite3
import sys

CHUNK = re.compile(r"\[(\d+)/(\d+)\]\n(.*?)(?=\[javascript_tool:|\Z)", re.S)
JD_ID = re.compile(r"page: jd \| id: (\d+)")


def tool_texts(path):
    """Yield the text of each tool result in a transcript, in order."""
    with open(path, errors="replace") as f:
        for line in f:
            if "page: jd" not in line and "[javascript_tool" not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            content = (entry.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                inner = block.get("content")
                if isinstance(inner, str):
                    yield inner
                elif isinstance(inner, list):
                    yield "\n".join(b.get("text", "") for b in inner if isinstance(b, dict))


def collect_jds(texts):
    """Return {job id: text}. Chunks without a header belong to the last job seen."""
    parts, current = {}, None
    for text in texts:
        for k, n, body in CHUNK.findall(text):
            found = JD_ID.search(body)
            if found:
                current = found.group(1)
            if current:
                parts.setdefault(current, {})[int(k)] = body.strip()
    return {i: "\n".join(c[k] for k in sorted(c)) for i, c in parts.items()}


def main():
    run_id = sys.argv[1]
    project = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    root = os.path.expanduser(
        sys.argv[2] if len(sys.argv) > 2
        else "~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", project))
    jds = {}
    for path in sorted(glob.glob(os.path.join(root, "*.jsonl")), key=os.path.getmtime):
        jds.update(collect_jds(tool_texts(path)))

    db = sqlite3.connect("data/tracker.db")
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "select * from jobs where run_id=? and score is not null", (run_id,)).fetchall()

    final, score = [], []
    for r in rows:
        card = "|".join(str(r[c] or "") for c in
                        ("id", "title", "company", "exp", "salary", "location", "posted",
                         "rating", "tags"))
        score.append({"id": r["id"], "card": f"{card}|d{r['det']}", "det": r["det"],
                      "stored": r["score"], "status": r["status"],
                      "reason": r["reason"] or ""})
        reason = r["reason"] or ""
        if r["status"] in ("applied", "company_site_queued"):
            gold = "pass"
        elif reason.startswith("jd:"):
            gold = "skip"
        else:
            continue
        if r["id"] in jds:
            final.append({"id": r["id"], "jd": jds[r["id"]], "gold": gold, "reason": reason})

    questions = {}
    for r in db.execute("select id, company, answers from jobs where answers is not null"):
        for a in json.loads(r["answers"]):
            questions.setdefault(a["question"], []).append(a["answer"])

    os.makedirs("data/evals", exist_ok=True)
    json.dump(final, open("data/evals/final.json", "w"), indent=1)
    json.dump(score, open("data/evals/score.json", "w"), indent=1)
    json.dump(questions, open("data/evals/questions-seen.json", "w"), indent=1)
    print(f"jds {len(jds)} | final cases {len(final)} "
          f"(pass {sum(c['gold'] == 'pass' for c in final)}, "
          f"skip {sum(c['gold'] == 'skip' for c in final)}) | "
          f"score cases {len(score)} | questions {len(questions)}")


if __name__ == "__main__":
    main()
