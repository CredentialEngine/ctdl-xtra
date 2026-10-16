from xtra.ctid import CTID_FORM, CtidService, Ledger

ORG = "ce-57603921-78ce-455c-88b5-00506fb33701"


def test_minted_once_and_remembered(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = CtidService(Ledger(path)).ctid_for(ORG, "ACCT 20103")
    assert CTID_FORM.match(first)
    assert CtidService(Ledger(path)).ctid_for(ORG, "ACCT 20103") == first  # a fresh service, same ledger
    assert len(path.read_text().splitlines()) == 1  # nothing appended the second time


def test_non_breaking_space_finds_the_same_entry(tmp_path):
    service = CtidService(Ledger(tmp_path / "ledger.jsonl"))
    assert service.ctid_for(ORG, "ACCT 20103") == service.ctid_for(ORG, "ACCT 20103")


def test_different_courses_and_organisations_differ(tmp_path):
    service = CtidService(Ledger(tmp_path / "ledger.jsonl"))
    a = service.ctid_for(ORG, "ACCT 20103")
    assert a != service.ctid_for(ORG, "ACCT 20203")
    assert a != service.ctid_for("ce-other", "ACCT 20103")
