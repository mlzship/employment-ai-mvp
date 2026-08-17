from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginManifest


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"[\s_\-/]+", "", normalized)


@dataclass(frozen=True, slots=True)
class ConceptMapping:
    source_label: str
    concept_id: str
    canonical_label: str
    concept_type: str
    method: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_label": self.source_label,
            "concept_id": self.concept_id,
            "canonical_label": self.canonical_label,
            "concept_type": self.concept_type,
            "method": self.method,
            "confidence": self.confidence,
        }


class OntologyService:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.ontology_id = payload["ontology_id"]
        self.version = payload["version"]
        self._concepts: dict[str, dict[str, Any]] = {}
        self._aliases: dict[tuple[str, str], str] = {}
        for concept in payload.get("@graph", []):
            concept_id = concept["@id"]
            concept_type = concept["@type"]
            self._concepts[concept_id] = concept
            for label in [concept.get("label", ""), *concept.get("aliases", [])]:
                if label:
                    self._aliases[(concept_type, _key(label))] = concept_id

    def map(self, source_label: str, concept_type: str) -> ConceptMapping:
        raw = str(source_label or "").strip()
        concept_id = self._aliases.get((concept_type, _key(raw)))
        if concept_id:
            concept = self._concepts[concept_id]
            method = "exact" if _key(raw) == _key(concept["label"]) else "alias"
            return ConceptMapping(
                source_label=raw,
                concept_id=concept_id,
                canonical_label=concept["label"],
                concept_type=concept_type,
                method=method,
                confidence=1.0 if method == "exact" else 0.98,
            )
        digest = hashlib.sha1(f"{concept_type}:{raw}".encode()).hexdigest()[:10]
        return ConceptMapping(
            source_label=raw,
            concept_id=f"unmapped:{concept_type.lower()}:{digest}",
            canonical_label=raw,
            concept_type=concept_type,
            method="unmapped",
            confidence=0.0,
        )

    def normalize_person(self, person: dict[str, Any]) -> dict[str, Any]:
        result = dict(person)
        skill_mappings = [self.map(item, "Skill") for item in person.get("skills", [])]
        industry_mappings = [
            self.map(item, "Industry") for item in person.get("preferred_industries", [])
        ]
        result["canonical_skills"] = [item.concept_id for item in skill_mappings]
        result["canonical_industries"] = [item.concept_id for item in industry_mappings]
        result["semantic_evidence"] = {
            "ontology_id": self.ontology_id,
            "ontology_version": self.version,
            "skills": [item.as_dict() for item in skill_mappings],
            "industries": [item.as_dict() for item in industry_mappings],
        }
        return result

    def normalize_job(self, job: dict[str, Any]) -> dict[str, Any]:
        result = dict(job)
        skill_mappings = [self.map(item, "Skill") for item in job.get("required_skills", [])]
        occupation = self.map(job.get("job_title", ""), "Occupation")
        industry = self.map(job.get("industry", ""), "Industry")
        result["canonical_required_skills"] = [item.concept_id for item in skill_mappings]
        result["occupation_id"] = occupation.concept_id
        result["industry_id"] = industry.concept_id
        result["semantic_evidence"] = {
            "ontology_id": self.ontology_id,
            "ontology_version": self.version,
            "required_skills": [item.as_dict() for item in skill_mappings],
            "occupation": occupation.as_dict(),
            "industry": industry.as_dict(),
        }
        return result

    def health(self) -> dict[str, Any]:
        unmapped = sum(1 for concept_id in self._concepts if concept_id.startswith("unmapped:"))
        return {
            "status": "ok",
            "ontology_id": self.ontology_id,
            "version": self.version,
            "concepts": len(self._concepts),
            "unmapped": unmapped,
        }


class SemanticOntologyPlugin(Plugin):
    manifest = PluginManifest(
        id="semantic-ontology",
        version="1.0.0",
        name="最小人才本体",
        description="把技能、岗位和行业同义词映射为稳定概念ID，并保留来源与置信度",
        provides=("semantic.normalize",),
        requires=("data.quality",),
        permissions=("ontology:read", "snapshot:annotate"),
        events_in=("data.quality.checked",),
        events_out=("semantic.normalized",),
        cleanup_strategy=(
            "remove normalizer service; preserve versioned mappings embedded in snapshots"
        ),
    )

    def install(self, context: AppContext) -> None:
        service = OntologyService(context.settings.ontology_path)
        context.services.register("semantic.normalize", self.manifest.id, service)

    def health(self, context: AppContext) -> dict[str, Any]:
        return context.services.get("semantic.normalize").health()
