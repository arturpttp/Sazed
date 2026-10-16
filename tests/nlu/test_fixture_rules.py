"""Rules the labelled fixture must follow, checked without the model."""

from pathlib import Path

from sazed.nlu.normalize import normalize
from sazed.runtime.evaluation import dry_run_skills, load_cases

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nlu_cases.toml"


def test_no_fixture_phrase_copies_a_seed_example() -> None:
    apps, cases = load_cases(FIXTURE)
    seeds = {
        normalize(example)
        for skill in dry_run_skills(apps).skills
        for spec in skill.intents
        for example in spec.examples
    }
    assert [c.text for c in cases if normalize(c.text) in seeds] == []


def test_every_labelled_intent_exists() -> None:
    apps, cases = load_cases(FIXTURE)
    known = {spec.id for skill in dry_run_skills(apps).skills for spec in skill.intents}
    assert {c.intent for c in cases} - known - {"none"} == set()
