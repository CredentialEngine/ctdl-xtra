import json

from conftest import PROPERTIES

from review_ui.template import build_properties, load_properties


def test_build_properties_reads_sections_and_flags(tmp_path):
    csv_file = tmp_path / "t.csv"
    csv_file.write_text(
        "Property,Term,Definition,Specifications,Link,Controlled Vocabulary,Multiple Values,Sample\n"
        "Required Properties,,,,,,,\n"
        "Name,ceterms:name,d,,,,Single,x\n"
        "Learning Type,,d,,,,Single,Course\n"
        "Other,,,,,,,\n"
        "Keywords,ceterms:keyword,d,,,,Multiple,x\n"
    )
    props = build_properties(csv_file)
    assert [p["name"] for p in props] == ["Name", "Learning Type", "Keywords"]
    assert props[0]["required"] and props[0]["term"] == "ceterms:name"
    assert props[1]["term"] is None
    assert not props[2]["required"] and props[2]["multiple"]
    assert props[2]["section"] == "Other"


def test_shipped_properties_include_the_required_course_fields():
    required = {p.name for p in load_properties(PROPERTIES) if p.required}
    assert {"Learning Opportunity Name", "Description", "Subject Webpage"} <= required
    assert json.loads(PROPERTIES.read_text())  # valid json


def test_the_template_has_the_prerequisite_properties_and_not_their_retired_names():
    props = {p.name: p for p in load_properties(PROPERTIES)}
    assert props["Prerequisite"].term == "ceterms:prerequisite"
    assert props["Corequisite"].term == "ceterms:corequisite"
    assert props["Co-Prerequisite"].term == "ceterms:coPrerequisite"
    assert props["Learning Opportunity Type"].term == "ceterms:learningOpportunityType"
    assert props["Content Description"].term == "ceterms:contentDescription"
    for retired in ("Prerequisites", "Learning Part Type", "Learning Designation Type"):
        assert retired not in props


def test_every_property_name_in_the_template_is_unique():
    names = [p.name for p in load_properties(PROPERTIES)]
    assert len(names) == len(set(names)) == 132
