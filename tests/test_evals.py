import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "evals"))
import grade  # noqa: E402


def test_final_counts_wrong_applies_and_misses_apart():
    cases = [{"id": "1", "gold": "skip"}, {"id": "2", "gold": "pass"}, {"id": "3", "gold": "pass"}]
    preds = [{"id": "1", "decision": "pass", "reason": "x"}, {"id": "2", "decision": "skip"}]
    r = grade.grade_final(cases, preds)
    assert [w["id"] for w in r["wrong_apply"]] == ["1"]
    assert [m["id"] for m in r["missed"]] == ["2"]
    assert r["missing"] == ["3"]
    assert r["right"] == 0


def test_score_adds_det_and_uses_the_bar():
    cases = [
        {"id": "a", "status": "applied", "det": 30, "stored": 80},
        {"id": "b", "status": "skipped", "det": 30, "stored": 40},
        {"id": "c", "status": "skipped", "det": 30, "stored": 70},
    ]
    preds = [{"id": "a", "model": 30}, {"id": "b", "model": 40}, {"id": "c", "model": 50}]
    r = grade.grade_score(cases, preds)
    assert r["lost"] == ["a"]
    assert r["leaked"] == ["b"]
    assert r["recall"] == 0.0


def test_score_must_not_holds_a_job_that_queued_before():
    cases = [{"id": "c", "status": "skipped", "det": 30, "stored": 70}]
    r = grade.grade_score(cases, [{"id": "c", "model": 50}], must_not={"c"})
    assert r["leaked"] == ["c"]


def test_score_ignores_a_final_check_skip_that_is_not_listed():
    cases = [{"id": "c", "status": "skipped", "det": 30, "stored": 70}]
    r = grade.grade_score(cases, [{"id": "c", "model": 50}])
    assert r["leaked"] == []


def test_a_missing_score_counts_as_lost():
    cases = [{"id": "a", "status": "applied", "det": 30, "stored": 80}]
    r = grade.grade_score(cases, [])
    assert r["lost"] == ["a"] and r["missing"] == ["a"]


def test_screener_answer_on_a_blank_case_is_an_overclaim():
    cases = [{"id": "s", "q": "q", "blank": True}]
    assert grade.grade_screener(cases, [{"id": "s", "answer": "7"}])["overclaim"]
    assert grade.grade_screener(cases, [{"id": "s", "answer": grade.BLANK}])["right"] == 1


def test_screener_refusal_is_not_a_wrong_answer():
    cases = [{"id": "s", "q": "q", "accept": "^3"}]
    r = grade.grade_screener(cases, [{"id": "s", "answer": grade.BLANK}])
    assert r["refused"] and not r["wrong"]


def test_screener_forbid_catches_a_plain_yes_only():
    cases = [{"id": "s", "q": "q", "forbid": r"^yes\.?$"}]
    assert grade.grade_screener(cases, [{"id": "s", "answer": "Yes"}])["overclaim"]
    assert grade.grade_screener(cases, [{"id": "s", "answer": "Yes, 3 years, some at work"}])["right"] == 1


def test_screener_max_len():
    cases = [{"id": "s", "q": "q", "accept": "a", "max_len": 3}]
    assert grade.grade_screener(cases, [{"id": "s", "answer": "aaaa"}])["wrong"]


def test_parse_json_list_handles_a_fence():
    assert grade.parse_json_list('Here:\n```json\n[{"id": "1"}]\n```') == [{"id": "1"}]
