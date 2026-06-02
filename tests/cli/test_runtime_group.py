from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()


def test_runtime_host_help() -> None:
    result = runner.invoke(app, ["runtime", "host", "--help"])
    assert result.exit_code == 0, result.output
    assert "--control-plane-url" in result.output


def test_runtime_devcontainer_help() -> None:
    result = runner.invoke(app, ["runtime", "devcontainer", "--help"])
    assert result.exit_code == 0, result.output
    assert "--devcontainer-id" in result.output


def test_old_flat_names_removed() -> None:
    assert runner.invoke(app, ["host-runtime", "--help"]).exit_code != 0
    assert runner.invoke(app, ["devcontainer-runtime", "--help"]).exit_code != 0
