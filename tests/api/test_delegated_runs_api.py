def test_delegated_runs_empty_for_known_devcontainer(client):
    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    resp = client.get(f"/api/v1/devcontainers/{created['id']}/delegated-runs")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_delegated_runs_404_for_unknown_devcontainer(client):
    resp = client.get("/api/v1/devcontainers/does-not-exist/delegated-runs")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_delegated_runs_returns_recorded_items(client):
    from vibing_protocol import DelegatedRunItem

    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    client.app.state.live_state.set_delegated_runs(
        created["id"],
        [DelegatedRunItem(
            run_id="r1", harness="codex", model="m", status="running",
            started_at="2026-06-20T00:00:00+00:00",
        )],
    )
    resp = client.get(f"/api/v1/devcontainers/{created['id']}/delegated-runs")
    assert resp.status_code == 200
    assert [i["run_id"] for i in resp.json()["items"]] == ["r1"]
