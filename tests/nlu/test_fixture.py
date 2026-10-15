from pathlib import Path

import pytest

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.core.policy import Thresholds
from sazed.nlu.matcher import IntentMatcher
from sazed.runtime.config import DEFAULT_MODEL_DIR, Config
from sazed.runtime.evaluation import (
    MAX_FALSE_EXECUTE,
    MIN_ACCURACY,
    DryRunPorts,
    evaluate,
    load_cases,
)
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill

pytestmark = pytest.mark.model
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nlu_cases.toml"


def test_fixture_meets_accuracy_and_false_execute_thresholds_with_default_config() -> None:
    if not (DEFAULT_MODEL_DIR / "model.onnx").exists():
        pytest.fail("model missing: run `uv run python scripts/fetch_model.py` first")
    app_names, cases = load_cases(FIXTURE)
    assert len(cases) >= 80
    index = IntentMatcher(OnnxEmbedder(DEFAULT_MODEL_DIR))
    ports = DryRunPorts(app_names)
    for skill in (AppsSkill(ports, ports), VolumeSkill(ports)):
        for spec in skill.intents:
            index.add_examples(spec.id, spec.examples)
    nlu = Config().nlu
    report = evaluate(
        cases,
        index=index,
        app_names=app_names,
        thresholds=Thresholds(nlu.t_exec, nlu.t_confirm, nlu.g_min),
    )
    detail = "\n".join(
        f"{r.case.text!r}: expected {r.case.intent}, top {r.top_intent}, "
        f"{type(r.decision).__name__}"
        for r in report.false_executes() + report.misranked()
    )
    assert report.accuracy >= MIN_ACCURACY, detail
    assert report.false_execute_rate <= MAX_FALSE_EXECUTE, detail
