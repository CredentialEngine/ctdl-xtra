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
