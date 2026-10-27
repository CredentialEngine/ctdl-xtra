import pytest

from golden_datasets.cli import build_parser, main


def test_help_lists_every_command_group(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for cmd in ["init", "assets", "import-v2", "extract", "check", "sql", "rule", "pages", "prompt", "golden",
                "sync", "serve"]:
        assert cmd in out


def test_rule_subcommands_parse():
    ap = build_parser()
    for argv in (["rule", "try", "d.json"], ["rule", "publish", "d.json", "--force"], ["rule", "draft", "a", "b"]):
        args = ap.parse_args([*argv, "--root", "/tmp/x", "--catalog", "avc"])
        assert args._target.startswith("golden_datasets.loop:")


def test_env_file_fills_unset_variables(tmp_path, monkeypatch):
    from golden_datasets.cli import load_env_file

    (tmp_path / "golden-datasets.env").write_text(
        "# a comment\nGOLDEN_DATASETS_ROOT='/from/file'\nexport GOLDEN_DATASETS_CATALOG=avc\n")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.delenv("GOLDEN_DATASETS_ROOT", raising=False)
    monkeypatch.setenv("GOLDEN_DATASETS_CATALOG", "wvu")  # the environment wins
    assert load_env_file(sub) == tmp_path / "golden-datasets.env"
    import os
    assert os.environ["GOLDEN_DATASETS_ROOT"] == "/from/file" and os.environ["GOLDEN_DATASETS_CATALOG"] == "wvu"
