import json

from vibing_cli.client import render


def test_render_json_outputs_raw(capsys) -> None:
    render.render({"id": "x"}, as_json=True)
    assert json.loads(capsys.readouterr().out) == {"id": "x"}


def test_render_list_prints_table(capsys) -> None:
    render.render({"items": [{"id": "a", "name": "one"}]}, as_json=False)
    out = capsys.readouterr().out
    assert "id" in out and "name" in out and "one" in out


def test_render_empty_list(capsys) -> None:
    render.render({"items": []}, as_json=False)
    assert "No results" in capsys.readouterr().out


def test_render_object_prints_fields(capsys) -> None:
    render.render({"id": "x", "status": "running"}, as_json=False)
    out = capsys.readouterr().out
    assert "status" in out and "running" in out


def test_render_none_is_silent(capsys) -> None:
    render.render(None, as_json=False)
    assert capsys.readouterr().out == ""
