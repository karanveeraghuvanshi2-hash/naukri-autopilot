"""Graders for the replay evals. Pure functions, stdlib only."""
import re

BLANK = "(unanswered)"


def _by_id(preds):
    return {str(p.get("id")): p for p in preds}


def grade_final(cases, preds):
    """Gold is the decision on the job page: pass or skip."""
    got = _by_id(preds)
    wrong_apply, missed, missing = [], [], []
    for c in cases:
        p = got.get(c["id"])
        if p is None:
            missing.append(c["id"])
        elif p.get("decision") != c["gold"]:
            (wrong_apply if c["gold"] == "skip" else missed).append(
                {"id": c["id"], "said": p.get("reason", "")})
    n = len(cases)
    right = n - len(wrong_apply) - len(missed) - len(missing)
    return {"cases": n, "right": right, "accuracy": round(right / n, 3) if n else 0.0,
            "wrong_apply": wrong_apply, "missed": missed, "missing": missing}


def grade_score(cases, preds, threshold=65, must_not=()):
    """A job with an application or a company-site queue must queue.

    `must_not` and jobs the stored score left below the bar must not. Jobs that
    queued and then failed the final check are unlabelled at the card.
    """
    got = _by_id(preds)
    must_queue = [c for c in cases if c["status"] in ("applied", "company_site_queued")]
    negatives = [c for c in cases if c["id"] in must_not
                 or (c["status"] == "skipped" and (c.get("stored") or 0) < threshold)]
    total = lambda c: (got.get(c["id"]) or {}).get("model", 0) + (c.get("det") or 0)
    lost = [c["id"] for c in must_queue if total(c) < threshold]
    leaked = [c["id"] for c in negatives if total(c) >= threshold]
    scored = [c for c in cases if c["id"] in got and c.get("stored") is not None]
    same = sum((total(c) >= threshold) == (c["stored"] >= threshold) for c in scored)
    drift = [abs(total(c) - c["stored"]) for c in scored]
    return {
        "recall": round(1 - len(lost) / len(must_queue), 3) if must_queue else 1.0,
        "lost": lost,
        "leak_rate": round(len(leaked) / len(negatives), 3) if negatives else 0.0,
        "leaked": leaked,
        "bar_agreement": round(same / len(scored), 3) if scored else 0.0,
        "mean_drift": round(sum(drift) / len(drift), 1) if drift else 0.0,
        "missing": [c["id"] for c in cases if c["id"] not in got],
    }


def grade_screener(cases, preds):
    """`overclaim` counts answers that say more than the sources: the 100% rule."""
    got = _by_id(preds)
    wrong, overclaim, refused, missing = [], [], [], []
    for c in cases:
        if c["id"] not in got:
            missing.append(c["id"])
            continue
        answer = str(got[c["id"]].get("answer", "")).strip()
        row = {"id": c["id"], "q": c["q"], "said": answer}
        if c.get("blank"):
            if answer != BLANK:
                overclaim.append(row)
        elif answer == BLANK:
            refused.append(row)
        elif c.get("forbid") and re.search(c["forbid"], answer, re.I):
            overclaim.append(row)
        elif c.get("accept") and not re.search(c["accept"], answer, re.I):
            wrong.append(row)
        elif c.get("max_len") and len(answer) > c["max_len"]:
            wrong.append(row)
    n = len(cases)
    right = n - len(wrong) - len(overclaim) - len(refused) - len(missing)
    return {"cases": n, "right": right, "accuracy": round(right / n, 3) if n else 0.0,
            "overclaim": overclaim, "refused": refused, "wrong": wrong, "missing": missing}


def parse_json_list(text):
    """Pull the JSON list out of a model reply, with or without a code fence."""
    import json
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON list in reply")
    return json.loads(text[start:end + 1])
