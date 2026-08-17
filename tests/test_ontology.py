from pathlib import Path

from employment_ai.plugins.ontology import OntologyService

ONTOLOGY = Path(__file__).resolve().parents[1] / "data/ontology/employment_ontology.json"


def test_aliases_map_to_stable_concept_ids() -> None:
    service = OntologyService(ONTOLOGY)

    cnc = service.map("CNC操作", "Skill")
    canonical = service.map("数控操作", "Skill")

    assert cnc.concept_id == "skill:cnc_operation"
    assert canonical.concept_id == cnc.concept_id
    assert cnc.method == "alias"
    assert cnc.confidence == 0.98


def test_unmapped_values_are_explicit_and_source_is_preserved() -> None:
    service = OntologyService(ONTOLOGY)
    person = service.normalize_person(
        {
            "person_id": "P-DEMO",
            "skills": ["CNC操作", "自定义新技能"],
            "preferred_industries": ["机械制造"],
        }
    )

    assert person["skills"] == ["CNC操作", "自定义新技能"]
    assert person["canonical_skills"][0] == "skill:cnc_operation"
    assert person["canonical_skills"][1].startswith("unmapped:skill:")
    assert person["semantic_evidence"]["ontology_version"] == "1.0.0"
    assert person["semantic_evidence"]["skills"][1]["method"] == "unmapped"
