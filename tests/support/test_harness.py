from support.harness import build_harness


def test_harness_wires_fakes_into_the_assistant() -> None:
    h = build_harness({"volume em 30": {"volume_definir": 0.97}})
    h.say("volume em 30")
    assert h.audio.volume == 30
    assert len(h.store.episodes(5)) == 1


def test_harness_clock_drives_the_assistant() -> None:
    h = build_harness()
    h.clock.advance(5)
    h.say("nada")
    assert h.store.episodes(1)[0].episode.at == h.clock.now
