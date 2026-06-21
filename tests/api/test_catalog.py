from vibing_api.api.schemas.devcontainers import DevcontainerSource
from vibing_api.core.catalog import DevcontainerCatalog
from vibing_api.core.discovery import DiscoveredDevcontainer, discovered_id
from vibing_api.repositories.devcontainers import DevcontainerRecord


def _manual(id_: str, path: str) -> DevcontainerRecord:
    return DevcontainerRecord(id_, "manual-" + id_, path, "t0", "t1")


def _catalog(
    records: list[DevcontainerRecord], discovered: list[DiscoveredDevcontainer]
) -> DevcontainerCatalog:
    return DevcontainerCatalog(
        list_records=lambda: records,
        get_record=lambda i: next((r for r in records if r.id == i), None),
        scanner=lambda: discovered,
    )


def test_list_merges_and_tags_source() -> None:
    record = _manual("m1", "/a")
    disc = DiscoveredDevcontainer(discovered_id("/b"), "b", "/b")
    cat = _catalog([record], [disc])
    by_id = {r.id: r for r in cat.list()}
    assert by_id["m1"].source == DevcontainerSource.MANUAL
    assert by_id[disc.id].source == DevcontainerSource.DISCOVERED
    assert by_id[disc.id].created_at is None


def test_manual_hides_discovered_with_same_path() -> None:
    record = _manual("m1", "/shared")
    disc = DiscoveredDevcontainer(discovered_id("/shared"), "shared", "/shared")
    cat = _catalog([record], [disc])
    items = cat.list()
    assert [r.id for r in items] == ["m1"]


def test_get_resolves_manual_and_discovered() -> None:
    record = _manual("m1", "/a")
    disc = DiscoveredDevcontainer(discovered_id("/b"), "b", "/b")
    cat = _catalog([record], [disc])
    assert cat.get("m1").source == DevcontainerSource.MANUAL
    assert cat.get(disc.id).source == DevcontainerSource.DISCOVERED
    assert cat.get("missing") is None
