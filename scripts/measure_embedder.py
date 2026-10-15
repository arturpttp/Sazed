"""Measure the embedder's RAM and latency on this machine.

Usage: uv run python scripts/measure_embedder.py
"""

import statistics
import time

import psutil

from sazed.adapters.onnx.embedder import OnnxEmbedder
from sazed.runtime.config import DEFAULT_MODEL_DIR
from sazed.runtime.evaluation import DryRunPorts
from sazed.skills.pc.apps import AppsSkill
from sazed.skills.pc.volume import VolumeSkill


def main() -> None:
    process = psutil.Process()
    before = process.memory_info().rss
    started = time.perf_counter()
    embedder = OnnxEmbedder(DEFAULT_MODEL_DIR)
    load_s = time.perf_counter() - started
    after_load = process.memory_info().rss

    ports = DryRunPorts([])
    skills = (AppsSkill(ports, ports), VolumeSkill(ports))
    seeds = [e for skill in skills for spec in skill.intents for e in spec.examples]
    started = time.perf_counter()
    embedder.embed(seeds)
    seeds_s = time.perf_counter() - started

    timings = []
    for _ in range(200):
        started = time.perf_counter()
        embedder.embed(["abre o google chrome pra mim"])
        timings.append((time.perf_counter() - started) * 1000)
    variant = (DEFAULT_MODEL_DIR / "VARIANT").read_text(encoding="utf-8").strip()
    print(f"variant: {variant}")
    total_mb = process.memory_info().rss / 1e6
    print(
        f"load: {load_s:.2f} s, RSS +{(after_load - before) / 1e6:.0f} MB, total {total_mb:.0f} MB"
    )
    print(f"{len(seeds)} seed examples: {seeds_s * 1000:.0f} ms")
    print(
        f"single sentence: median {statistics.median(timings):.1f} ms,"
        f" p95 {sorted(timings)[189]:.1f} ms"
    )


if __name__ == "__main__":
    main()
