from vibing_protocol import DelegatedRunItem, DelegatedRunsEnvelope


def test_delegated_runs_envelope_roundtrip():
    env = DelegatedRunsEnvelope(
        devcontainer_id="dc-1",
        items=[
            DelegatedRunItem(
                run_id="run-1",
                harness="codex",
                model="gpt-5-codex",
                status="running",
                started_at="2026-06-20T00:00:00+00:00",
            )
        ],
    )
    dumped = env.model_dump()
    assert dumped["type"] == "delegated_runs"
    again = DelegatedRunsEnvelope.model_validate(dumped)
    assert again.items[0].run_id == "run-1"
    assert again.items[0].result is None and again.items[0].error is None
