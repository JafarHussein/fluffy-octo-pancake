#!/usr/bin/env python3
"""CareerForge resume strategy engine (hardened v1.1).

Reads a candidate profile from PostgreSQL, ranks evidence against a job description,
and writes output/strategy/Resume_Strategy_Report.json.

Environment variables:
  POSTGRES_HOST (default 127.0.0.1), POSTGRES_PORT (default 5433),
  POSTGRES_DB (default careerforge), POSTGRES_USER (default careerforge_app),
  POSTGRES_PASSWORD (required unless provided by libpq), CAREERFORGE_PROFILE_ID (optional).

The engine deliberately uses transparent lexical/concept heuristics rather than claiming
that it understands semantics like a language model. Review the report before using it.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Allow unit tests and offline validation without psycopg installed.
    psycopg = None
    dict_row = None

ROOT = Path(__file__).resolve().parents[2] if Path(__file__).resolve().parent.name == "resume" else Path.cwd()
CONFIG_PATH = ROOT / "config" / "resume-strategy.v1.json"
JOB_DESCRIPTION_PATH = ROOT / "input" / "job_description.txt"
OUTPUT_PATH = ROOT / "output" / "strategy" / "Resume_Strategy_Report.json"

# All tunable defaults, fallbacks, and penalties live here.
POLICY: dict[str, Any] = {
    "version": "1.1.0",
    "default_profile_version": 1,
    "max_job_description_chars": 100_000,
    "max_selected_items": 22,
    "max_omitted_items": 100,
    "default_recommended_pages": 2,
    "minimum_recommended_pages": 1,
    "maximum_recommended_pages": 2,
    "unknown_date_recency_score": 65.0,
    "evidence_base_score": 35.0,
    "evidence_action_bonus": 18.0,
    "evidence_detail_bonus": 12.0,
    "evidence_result_bonus": 15.0,
    "evidence_cap": 100.0,
    "impact_base_score": 35.0,
    "impact_quantity_bonus": 25.0,
    "impact_scale_bonus": 15.0,
    "impact_outcome_bonus": 15.0,
    "impact_cap": 100.0,
    "recency_half_life_years": 5.0,
    "recency_floor": 45.0,
    "recency_cap": 100.0,
    "minimum_dimension_score": 1.0,
    "related_concept_default_weight": 0.35,
    "minimum_related_concept_weight": 0.0,
    "maximum_related_concept_weight": 0.85,
    "direct_match_weight": 1.0,
    "must_have_multiplier": 1.30,
    "preferred_multiplier": 1.12,
    "minimum_requirement_priority": 0.25,
    "maximum_requirement_priority": 1.0,
    "sentence_context_radius": 0,
    "minimum_relevance_score": 0.0,
    "fallback_relevance_score": None,
    "score_weights": {
        "jobRelevance": 0.30,
        "evidenceStrength": 0.25,
        "demonstratedImpact": 0.20,
        "differentiation": 0.15,
        "recency": 0.10,
    },
    "section_limits": {
        "experience": 4, "projects": 4, "skills": 10, "education": 2,
        "certifications": 5, "hackathons": 3,
    },
    "section_priority": [
        "experience", "projects", "technical_skills", "education", "certifications", "hackathons"
    ],
}

LOG_LEVEL = os.getenv("CAREERFORGE_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("careerforge.strategy")

# Canonical concept keys with phrase aliases. Keep these explicit and auditable.
CONCEPTS: dict[str, dict[str, Any]] = {
    "python": {"aliases": ["python", "python programming", "python development"]},
    "fastapi": {"aliases": ["fastapi", "fast api"], "related": {"python": 0.65, "python web framework": 0.65, "rest api": 0.35}},
    "django": {"aliases": ["django"], "related": {"python": 0.65, "python web framework": 0.65}},
    "flask": {"aliases": ["flask"], "related": {"python": 0.65, "python web framework": 0.65}},
    "python web framework": {"aliases": ["python web framework", "python web frameworks", "web framework using python"], "related": {"fastapi": 0.35, "django": 0.35, "flask": 0.35}},
    "java": {"aliases": ["java", "java programming"]},
    "spring boot": {"aliases": ["spring boot", "springboot"], "related": {"java": 0.65, "rest api": 0.35}},
    "rest api": {"aliases": ["rest api", "restful api", "rest apis", "api development", "web api", "web apis"], "related": {"fastapi": 0.35, "spring boot": 0.35}},
    "api design": {"aliases": ["api design", "api development", "api integration"]},
    "postgresql": {"aliases": ["postgresql", "postgres", "psql"], "related": {"sql": 0.65, "database": 0.35}},
    "mysql": {"aliases": ["mysql"], "related": {"sql": 0.65, "database": 0.35}},
    "sql": {"aliases": ["sql", "structured query language"], "related": {"postgresql": 0.35, "mysql": 0.35, "database": 0.35}},
    "mongodb": {"aliases": ["mongodb", "mongo db"], "related": {"nosql": 0.65, "database": 0.35}},
    "nosql": {"aliases": ["nosql", "no sql database", "document database"], "related": {"mongodb": 0.35, "database": 0.35}},
    "database": {"aliases": ["database", "databases", "database design", "data modeling", "data modelling"]},
    "git": {"aliases": ["git", "github", "version control", "source control"]},
    "testing": {"aliases": ["testing", "unit tests", "integration tests", "test automation", "pytest", "junit"]},
    "debugging": {"aliases": ["debugging", "troubleshooting", "root cause analysis"]},
    "docker": {"aliases": ["docker", "containerization", "containerisation", "containers"]},
    "kubernetes": {"aliases": ["kubernetes", "k8s", "container orchestration"]},
    "linux": {"aliases": ["linux", "linux administration", "linux system administration"]},
    "cloud": {"aliases": ["cloud", "cloud computing", "cloud infrastructure", "aws", "azure", "gcp"]},
    "security": {"aliases": ["security", "cybersecurity", "information security", "access control"]},
    "scalability": {"aliases": ["scalability", "scalable", "high availability", "performance optimization", "performance optimisation"]},
    "documentation": {"aliases": ["documentation", "technical documentation", "runbooks"]},
    "node.js": {"aliases": ["node.js", "nodejs", "node js"]},
    "typescript": {"aliases": ["typescript", "type script"]},
    "javascript": {"aliases": ["javascript", "java script"]},
    "react": {"aliases": ["react", "react.js", "reactjs"]},
    "communication": {"aliases": ["communication", "stakeholder communication", "user support", "customer support"]},
    "agile": {"aliases": ["agile", "scrum", "kanban", "sprint planning"]},
    "automation": {"aliases": ["automation", "automated workflow", "workflow automation", "n8n"]},
    "machine learning": {"aliases": ["machine learning", "scikit-learn", "sklearn", "predictive modeling", "predictive modelling"]},
    "data analysis": {"aliases": ["data analysis", "pandas", "data analytics", "data processing"]},
}

ITEM_DEFINITIONS: dict[str, dict[str, Any]] = {
    "experiences": {"section": "experience", "title": ("job_title", "title", "role", "position"), "organization": ("organization", "company", "employer"), "description": ("description", "summary", "responsibilities", "details"), "start_date": ("start_date", "startDate", "date_started"), "end_date": ("end_date", "endDate", "date_ended"), "dates": ("start_date", "end_date")},
    "projects": {"section": "projects", "title": ("name", "title", "project_name"), "organization": ("organization", "client", "company"), "description": ("description", "summary", "details", "technologies"), "start_date": ("start_date", "startDate"), "end_date": ("end_date", "endDate"), "dates": ("start_date", "end_date")},
    "skills": {"section": "technical_skills", "title": ("name", "skill", "skill_name", "title"), "organization": ("category", "group", "skill_category"), "description": ("description", "details", "proficiency", "level"), "start_date": (), "end_date": (), "dates": ()},
    "education": {"section": "education", "title": ("degree", "qualification", "program", "title"), "organization": ("institution", "school", "university"), "description": ("description", "field_of_study", "result", "grade"), "start_date": ("start_date", "startDate"), "end_date": ("end_date", "expected_graduation", "graduation_date", "endDate"), "dates": ("start_date", "end_date")},
    "certifications": {"section": "certifications", "title": ("name", "title", "certification_name"), "organization": ("issuer", "provider", "organization"), "description": ("description", "details", "credential_id"), "start_date": ("issued_at", "issue_date", "date_earned"), "end_date": ("expires_at", "expiry_date"), "dates": ("issued_at", "expires_at")},
    # Hackathons commonly have one event_date. It is a single-date field, not a fake start/end tuple.
    "hackathons": {"section": "hackathons", "title": ("name", "title", "event_name"), "organization": ("organizer", "organization", "host"), "description": ("description", "details", "achievement", "result", "role"), "start_date": ("event_date", "start_date", "date"), "end_date": ("end_date",), "single_date": ("event_date", "date"), "dates": ("event_date",)},
}

ACTION_TERMS = ("built", "developed", "implemented", "designed", "created", "deployed", "maintained", "automated", "integrated", "configured", "managed", "led", "tested", "optimized", "optimised", "supported", "resolved", "delivered", "analyzed", "analysed", "documented", "migrated", "improved")
RESULT_TERMS = ("reduced", "increased", "improved", "enabled", "delivered", "launched", "supported", "resolved", "automated", "streamlined", "secured", "accelerated", "saved", "completed", "finalist", "winner", "deployed")
SCALE_TERMS = ("daily", "weekly", "monthly", "users", "customers", "records", "requests", "transactions", "services", "teams", "departments", "sites", "counties", "markets", "workflow", "workflows", "production", "organization-wide", "organization wide")
MUST_HAVE_PHRASES = ("must have", "must-have", "required", "requirements include", "you need", "essential", "minimum qualifications", "mandatory")
PREFERRED_PHRASES = ("preferred", "nice to have", "nice-to-have", "bonus", "desirable", "ideally", "would be an advantage", "a plus")


def normalize_text(value: Any) -> str:
    """Normalize arbitrary text-like values safely for matching."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        value = stringify(value)
    elif isinstance(value, (date, datetime)):
        value = value.isoformat()
    else:
        value = str(value)
    value = value.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    value = re.sub(r"\s+", " ", value.strip().lower())
    return value


def stringify(value: Any) -> str:
    """Stable stringification for JSONB, arrays, dates and unexpected driver values."""
    if value is None:
        return ""
    if isinstance(value, str):
        # Parse JSON-encoded strings only when they look like complete JSON structures.
        candidate = value.strip()
        if candidate.startswith(("{", "[")):
            try:
                parsed = json.loads(candidate)
                return json.dumps(parsed, ensure_ascii=False, sort_keys=True) if isinstance(parsed, (dict, list)) else str(parsed)
            except (json.JSONDecodeError, TypeError):
                return value.strip()
        return value.strip()
    if isinstance(value, (dict, list, tuple, set)):
        if isinstance(value, set):
            value = sorted(value, key=str)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def first_value(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = stringify(value)
    if not raw:
        return None
    # Accept ISO dates and common timestamp strings; don't guess ambiguous formats.
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    words = re.escape(normalize_text(phrase)).replace(r"\ ", r"\s+")
    return re.compile(r"(?<![a-z0-9+#])" + words + r"(?![a-z0-9+#])", re.IGNORECASE)


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase_pattern(phrase).search(normalize_text(text)))


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Split on sentence punctuation and newlines while preserving offsets."""
    spans = []
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|\n|$)", text):
        sentence = match.group(0).strip()
        if sentence:
            spans.append((match.start(), match.end(), sentence))
    return spans or ([(0, len(text), text)] if text else [])


def localized_context(text: str, phrase: str, radius: int | None = None) -> str:
    """Return only the sentence containing the phrase and nearby sentence context."""
    normalized = normalize_text(text)
    pattern = phrase_pattern(phrase)
    match = pattern.search(normalized)
    if not match:
        return ""
    spans = sentence_spans(normalized)
    index = next((i for i, (start, end, _) in enumerate(spans) if start <= match.start() < end), None)
    if index is None:
        return normalized[max(0, match.start() - 100):min(len(normalized), match.end() + 100)]
    radius = POLICY["sentence_context_radius"] if radius is None else max(0, radius)
    lo, hi = max(0, index - radius), min(len(spans), index + radius + 1)
    return " ".join(span[2] for span in spans[lo:hi])


def get_aliases(concept: str) -> list[str]:
    spec = CONCEPTS.get(concept, {})
    aliases = spec.get("aliases", [concept])
    return list(dict.fromkeys([concept, *aliases]))


def find_job_requirements(job_description: str) -> list[dict[str, Any]]:
    """Identify explicit concepts and derive priority from localized language only."""
    jd = normalize_text(job_description)
    requirements: list[dict[str, Any]] = []
    for concept, spec in CONCEPTS.items():
        matches = []
        for alias in get_aliases(concept):
            for match in phrase_pattern(alias).finditer(jd):
                matches.append((match.start(), alias))
        if not matches:
            continue
        contexts = [localized_context(jd, alias) for _, alias in matches]
        must = any(any(contains_phrase(ctx, p) for p in MUST_HAVE_PHRASES) for ctx in contexts)
        preferred = any(any(contains_phrase(ctx, p) for p in PREFERRED_PHRASES) for ctx in contexts)
        # Frequency saturates to prevent repeated keyword stuffing from dominating.
        frequency = len(matches)
        priority = min(1.0, 0.55 + 0.15 * math.log2(1 + min(frequency, 4)))
        if must:
            priority *= POLICY["must_have_multiplier"]
        elif preferred:
            priority *= POLICY["preferred_multiplier"]
        priority = min(POLICY["maximum_requirement_priority"], max(POLICY["minimum_requirement_priority"], priority))
        requirements.append({
            "key": concept,
            "label": concept,
            "aliases": get_aliases(concept),
            "occurrences": frequency,
            "requiredOrPreferred": "required" if must else ("preferred" if preferred else "unspecified"),
            "jobSpecificPriority": round(priority, 4),
            "contexts": list(dict.fromkeys(contexts))[:3],
            "related": spec.get("related", {}),
        })
    requirements.sort(key=lambda item: (-item["jobSpecificPriority"], -item["occurrences"], item["key"]))
    return requirements


def concept_match_strength(text: str, requirement: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    """Return best direct/related match strength and transparent match labels."""
    haystack = normalize_text(text)
    key = str(requirement.get("key", ""))
    aliases = requirement.get("aliases") or get_aliases(key)
    for alias in aliases:
        if alias and contains_phrase(haystack, str(alias)):
            return POLICY["direct_match_weight"], [key], []
    related = requirement.get("related", {})
    related_matches: list[tuple[float, str]] = []
    for related_key, raw_weight in related.items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        weight = min(POLICY["maximum_related_concept_weight"], max(POLICY["minimum_related_concept_weight"], weight))
        related_aliases = get_aliases(str(related_key))
        if any(contains_phrase(haystack, alias) for alias in related_aliases):
            related_matches.append((weight, str(related_key)))
    if related_matches:
        related_matches.sort(reverse=True)
        best_weight = related_matches[0][0]
        related_labels = [label for weight, label in related_matches if weight == best_weight]
        return best_weight, [], related_labels
    return 0.0, [], []


def evidence_strength(text: str) -> float:
    """Score specificity and evidence without rewarding length or verification flags."""
    content = normalize_text(text)
    score = POLICY["evidence_base_score"]
    if any(contains_phrase(content, term) for term in ACTION_TERMS):
        score += POLICY["evidence_action_bonus"]
    # Specificity: distinct useful content signals, not raw character count.
    detail_signals = sum(bool(re.search(pattern, content)) for pattern in (
        r"\b(api|database|service|application|workflow|network|server|system|platform)\b",
        r"\b(python|java|sql|docker|linux|fastapi|django|flask|postgresql|mongodb)\b",
        r"\b(with|using|through|for|across|between)\b",
    ))
    if detail_signals >= 2:
        score += POLICY["evidence_detail_bonus"]
    if any(contains_phrase(content, term) for term in RESULT_TERMS):
        score += POLICY["evidence_result_bonus"]
    return min(POLICY["evidence_cap"], score)


def has_quantity_or_scale(text: str) -> bool:
    content = normalize_text(text)
    # Numeric and written quantities; avoid interpreting any arbitrary digit as impact.
    numeric_quantity = re.search(r"\b\d+(?:\.\d+)?\s*(%|percent|users?|customers?|records?|requests?|hours?|days?|weeks?|months?|years?|systems?|devices?|endpoints?|transactions?)\b", content)
    written_quantity = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|dozen|dozens|hundreds?|thousands?|millions?)\s+(of\s+)?(users?|customers?|records?|requests?|hours?|days?|weeks?|months?|years?|systems?|devices?|endpoints?|transactions?)\b", content)
    return bool(numeric_quantity or written_quantity)


def demonstrated_impact(text: str) -> float:
    content = normalize_text(text)
    score = POLICY["impact_base_score"]
    if has_quantity_or_scale(content):
        score += POLICY["impact_quantity_bonus"]
    if any(contains_phrase(content, term) for term in SCALE_TERMS):
        score += POLICY["impact_scale_bonus"]
    if any(contains_phrase(content, term) for term in RESULT_TERMS):
        score += POLICY["impact_outcome_bonus"]
    return min(POLICY["impact_cap"], score)


def recency_score(start_date: Any = None, end_date: Any = None, today: date | None = None) -> float:
    today = today or date.today()
    start = parse_date(start_date)
    end = parse_date(end_date)
    relevant = end or start
    if relevant is None:
        return float(POLICY["unknown_date_recency_score"])
    age_days = max(0, (today - relevant).days)
    age_years = age_days / 365.2425
    half_life = max(0.1, float(POLICY["recency_half_life_years"]))
    score = 100.0 * (0.5 ** (age_years / half_life))
    return max(float(POLICY["recency_floor"]), min(float(POLICY["recency_cap"]), score))


def differentiation_score(item: Mapping[str, Any], all_items: Sequence[Mapping[str, Any]]) -> float:
    """Reward evidence specificity and contribution; don't penalize shared core skills."""
    text = normalize_text(" ".join(stringify(item.get(k, "")) for k in ("title", "organization", "description")))
    signals = 0
    signals += int(any(contains_phrase(text, term) for term in ACTION_TERMS))
    signals += int(has_quantity_or_scale(text))
    signals += int(any(contains_phrase(text, term) for term in ("led", "owned", "designed", "architected", "founded", "implemented")))
    # Unique context is a small bonus, never a penalty for common required skills.
    own_terms = set(re.findall(r"[a-z][a-z0-9+#.]{3,}", text))
    other_terms: set[str] = set()
    for other in all_items:
        if other is item:
            continue
        other_text = normalize_text(" ".join(stringify(other.get(k, "")) for k in ("title", "organization", "description")))
        other_terms.update(re.findall(r"[a-z][a-z0-9+#.]{3,}", other_text))
    unique_ratio = len(own_terms - other_terms) / max(1, len(own_terms))
    return min(100.0, 40.0 + signals * 15.0 + unique_ratio * 15.0)


def weighted_geometric_score(dimensions: Mapping[str, float], weights: Mapping[str, float] | None = None) -> float:
    weights = weights or POLICY["score_weights"]
    valid = []
    for key, raw_weight in weights.items():
        try:
            weight = float(raw_weight)
            score = float(dimensions[key])
        except (KeyError, TypeError, ValueError):
            continue
        if weight > 0 and math.isfinite(weight) and math.isfinite(score):
            valid.append((max(POLICY["minimum_dimension_score"], min(100.0, score)), weight))
    if not valid:
        return 0.0
    weight_sum = sum(weight for _, weight in valid)
    if weight_sum <= 0:
        return 0.0
    return round(math.exp(sum((weight / weight_sum) * math.log(score) for score, weight in valid)), 2)


def item_relevance(item_text: str, requirements: Sequence[Mapping[str, Any]]) -> tuple[float, list[str], list[str]]:
    if not requirements:
        # No fabricated baseline: absence of recognized requirements means relevance is unknown/zero.
        fallback = POLICY["fallback_relevance_score"]
        return (float(fallback) if fallback is not None else 0.0), [], []
    weighted_total = 0.0
    weight_sum = 0.0
    matched: list[str] = []
    related: list[str] = []
    for req in requirements:
        strength, direct, related_keys = concept_match_strength(item_text, req)
        priority = float(req.get("jobSpecificPriority", 1.0))
        weighted_total += strength * priority
        weight_sum += priority
        matched.extend(direct)
        related.extend(related_keys)
    score = 100.0 * weighted_total / weight_sum if weight_sum else 0.0
    return round(score, 2), sorted(set(matched)), sorted(set(related))


def extract_item_value(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    value = first_value(row, keys)
    return stringify(value)


def build_items(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for table, definition in ITEM_DEFINITIONS.items():
        rows = profile.get(table, [])
        if isinstance(rows, str):
            try:
                rows = json.loads(rows)
            except json.JSONDecodeError:
                LOGGER.warning("Profile field %s was a string but not valid JSON; treating it as one record", table)
                rows = [{"name": rows}] if rows.strip() else []
        if isinstance(rows, Mapping):
            rows = [rows]
        if not isinstance(rows, (list, tuple)):
            LOGGER.warning("Profile field %s had unexpected type %s; skipping", table, type(rows).__name__)
            continue
        for index, raw_row in enumerate(rows):
            if not isinstance(raw_row, Mapping):
                LOGGER.warning("Skipping %s row %d with unexpected type %s", table, index, type(raw_row).__name__)
                continue
            title = extract_item_value(raw_row, definition.get("title", ()))
            organization = extract_item_value(raw_row, definition.get("organization", ()))
            description = extract_item_value(raw_row, definition.get("description", ()))
            if table == "skills" and not title:
                continue
            if not any((title, organization, description)):
                continue
            single_date_keys = definition.get("single_date", ())
            single_date = first_value(raw_row, single_date_keys) if single_date_keys else None
            start_date = first_value(raw_row, definition.get("start_date", ()))
            end_date = first_value(raw_row, definition.get("end_date", ()))
            if single_date is not None:
                start_date = single_date
                end_date = None
            item = {
                "type": table,
                "section": definition["section"],
                "title": title or organization or f"{table[:-1].title()} {index + 1}",
                "organization": organization,
                "description": description,
                "startDate": stringify(start_date),
                "endDate": stringify(end_date),
                "raw": dict(raw_row),
                "_sourceIndex": index,
            }
            items.append(item)
    return items


def public_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in ("type", "section", "title", "organization", "description", "startDate", "endDate", "score", "matchedKeywords", "relatedKeywords", "dimensions") if key in item}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        LOGGER.warning("Strategy config not found at %s; using centralized defaults", CONFIG_PATH)
        return {"version": POLICY["version"], "scoring": {"weights": POLICY["score_weights"]}}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Config root must be a JSON object")
        return value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.exception("Unable to read strategy config %s: %s", CONFIG_PATH, exc)
        raise


def load_job_description() -> str:
    if not JOB_DESCRIPTION_PATH.exists():
        raise FileNotFoundError(f"Job description not found: {JOB_DESCRIPTION_PATH}")
    text = JOB_DESCRIPTION_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Job description is empty: {JOB_DESCRIPTION_PATH}")
    if len(text) > POLICY["max_job_description_chars"]:
        raise ValueError(f"Job description exceeds configured limit of {POLICY['max_job_description_chars']} characters")
    return text


def _db_diagnostics(exc: BaseException) -> dict[str, Any]:
    diag: dict[str, Any] = {"exceptionType": type(exc).__name__}
    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    if sqlstate:
        diag["sqlstate"] = sqlstate
    diag_obj = getattr(exc, "diag", None)
    if diag_obj is not None:
        for source, target in (("severity_nonlocalized", "severity"), ("message_primary", "databaseMessage"), ("constraint_name", "constraint"), ("table_name", "table")):
            value = getattr(diag_obj, source, None)
            if value:
                diag[target] = str(value)[:300]
    diag["timeoutLikely"] = any(token in str(exc).lower() for token in ("timeout", "timed out", "could not connect", "connection refused"))
    return diag


def load_profile() -> dict[str, Any]:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Install psycopg[binary] in the project environment.")
    profile_id = os.getenv("CAREERFORGE_PROFILE_ID", "").strip()
    connection_args = {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5433")),
        "dbname": os.getenv("POSTGRES_DB", "careerforge"),
        "user": os.getenv("POSTGRES_USER", "careerforge_app"),
        "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "8")),
        "row_factory": dict_row,
    }
    password = os.getenv("POSTGRES_PASSWORD")
    if password:
        connection_args["password"] = password
    # Never log password, DSN, or any secret.
    LOGGER.info("Connecting to PostgreSQL host=%s port=%s dbname=%s user=%s connect_timeout=%ss profile_id=%s",
                connection_args["host"], connection_args["port"], connection_args["dbname"], connection_args["user"],
                connection_args["connect_timeout"], profile_id or "<not set>")
    try:
        with psycopg.connect(**connection_args) as conn:
            with conn.cursor() as cur:
                if profile_id:
                    cur.execute("SELECT to_jsonb(p) AS profile FROM career_profiles p WHERE p.id::text = %s", (profile_id,))
                else:
                    cur.execute("SELECT to_jsonb(p) AS profile FROM career_profiles p ORDER BY p.id LIMIT 3")
                records = cur.fetchall()
                if not records:
                    raise RuntimeError("No career profile found. Set CAREERFORGE_PROFILE_ID to an existing profile ID.")
                if not profile_id and len(records) > 1:
                    ids = [str((record.get("profile") or {}).get("id", "unknown")) for record in records]
                    raise RuntimeError(f"Multiple profiles found (sample IDs: {', '.join(ids)}). Set CAREERFORGE_PROFILE_ID explicitly.")
                profile = records[0].get("profile")
                if not isinstance(profile, dict):
                    raise RuntimeError("PostgreSQL returned an invalid career profile JSON object")
                profile_pk = profile.get("id")
                # Load related rows as JSONB to preserve native JSON types. Table names are fixed constants.
                for table in ITEM_DEFINITIONS:
                    cur.execute(f"SELECT COALESCE(jsonb_agg(to_jsonb(t) - 'id' - 'profile_id'), '[]'::jsonb) AS rows FROM {table} t WHERE t.profile_id::text = %s", (str(profile_pk),))
                    result = cur.fetchone() or {}
                    profile[table] = result.get("rows") or []
                return profile
    except Exception as exc:
        diagnostics = _db_diagnostics(exc)
        LOGGER.error("Database profile load failed diagnostics=%s", json.dumps(diagnostics, sort_keys=True))
        LOGGER.exception("Database profile load failed")
        raise


def configured_weights(config: Mapping[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    raw = (config.get("scoring") or {}).get("weights", {}) if isinstance(config.get("scoring"), Mapping) else {}
    raw = raw if isinstance(raw, Mapping) else {}
    for key, default in POLICY["score_weights"].items():
        try:
            weights[key] = max(0.0, float(raw.get(key, default)))
        except (TypeError, ValueError):
            weights[key] = float(default)
    if sum(weights.values()) <= 0:
        return dict(POLICY["score_weights"])
    return weights


def make_strategy(profile: Mapping[str, Any], job_description: str, config: Mapping[str, Any]) -> dict[str, Any]:
    requirements = find_job_requirements(job_description)
    items = build_items(profile)
    weights = configured_weights(config)
    scored: list[dict[str, Any]] = []
    for item in items:
        item_text = " ".join(stringify(item.get(k, "")) for k in ("title", "organization", "description"))
        relevance, matched, related = item_relevance(item_text, requirements)
        dimensions = {
            "jobRelevance": relevance,
            "evidenceStrength": evidence_strength(item_text),
            "demonstratedImpact": demonstrated_impact(item_text),
            "differentiation": differentiation_score(item, items),
            "recency": recency_score(item.get("startDate"), item.get("endDate")),
        }
        item["dimensions"] = {key: round(value, 2) for key, value in dimensions.items()}
        item["score"] = weighted_geometric_score(dimensions, weights)
        item["matchedKeywords"] = matched
        item["relatedKeywords"] = related
        item["_sortScore"] = item["score"]
        scored.append(item)
    scored.sort(key=lambda item: (-item["_sortScore"], item["section"], item["title"].lower()))

    limits = dict(POLICY["section_limits"])
    config_limits = config.get("selectionLimits", {})
    if isinstance(config_limits, Mapping):
        for key, value in config_limits.items():
            try:
                limits[str(key)] = max(0, int(value))
            except (TypeError, ValueError):
                LOGGER.warning("Ignoring invalid selection limit %s=%r", key, value)
    counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    max_items = int(POLICY["max_selected_items"])
    for item in scored:
        section = item["section"]
        always_include = section == "education"
        should_select = always_include or (item["score"] > 0 and counts[section] < limits.get(section, 3) and len(selected) < max_items)
        if should_select and len(selected) < max_items:
            selected.append(item)
            counts[section] += 1
        else:
            omitted.append(item)
    # Present in intentional section order, then by score within each section.
    section_order = {name: index for index, name in enumerate(POLICY["section_priority"])}
    selected.sort(key=lambda item: (section_order.get(item["section"], 99), -item["score"]))
    selected_keys = {(item["type"], item["_sourceIndex"]) for item in selected}
    omitted = [item for item in scored if (item["type"], item["_sourceIndex"]) not in selected_keys][:POLICY["max_omitted_items"]]
    pages = POLICY["default_recommended_pages"] if len(selected) > 12 else POLICY["minimum_recommended_pages"]
    pages = min(POLICY["maximum_recommended_pages"], max(POLICY["minimum_recommended_pages"], pages))
    profile_version = profile.get("profile_version", profile.get("version", POLICY["default_profile_version"]))
    report = {
        "strategyId": "careerforge-resume-strategy",
        "rulesetVersion": str(config.get("version", POLICY["version"])),
        "profileVersion": profile_version,
        "candidate": {
            "name": stringify(first_value(profile, ("full_name", "name", "candidate_name"))),
            "email": stringify(profile.get("email")),
            "phone": stringify(profile.get("phone")),
            "location": stringify(profile.get("location")),
        },
        "jobDescriptionPath": str(JOB_DESCRIPTION_PATH),
        "careerStage": "early_career",
        "careerStageConfidence": 0.78,
        "recommendedPages": pages,
        "preferredPages": POLICY["minimum_recommended_pages"],
        "selectedTextChars": sum(len(stringify(item.get("title"))) + len(stringify(item.get("organization"))) + len(stringify(item.get("description"))) for item in selected),
        "selectedEvidenceCount": len(selected),
        "omittedEvidenceCount": len(omitted),
        "recognizedJobRequirements": [{k: v for k, v in req.items() if k != "contexts"} for req in requirements],
        "relatedKeywords": sorted({key for item in selected for key in item.get("relatedKeywords", [])}),
        "scoringWeights": weights,
        "selectedEvidence": [public_item(item) for item in selected],
        "omittedEvidence": [public_item(item) for item in omitted],
        "missingEvidence": [
            {"requirement": req["key"], "label": req["label"], "priority": req["jobSpecificPriority"]}
            for req in requirements
            if not any(req["key"] in item.get("matchedKeywords", []) or req["key"] in item.get("relatedKeywords", []) for item in items)
        ],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Requirement detection and related-concept scoring are transparent heuristics, not full semantic understanding.",
            "Priority modifiers apply only to sentence-local context around a recognized concept.",
            "Review evidence and missing-evidence findings before generating or submitting a resume.",
        ],
    }
    return report


def main() -> int:
    try:
        config = load_config()
        job_description = load_job_description()
        profile = load_profile()
        report = make_strategy(profile, job_description, config)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
        temp_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")
        temp_path.replace(OUTPUT_PATH)
        LOGGER.info("RESUME_STRATEGY_SUCCESS candidate=%s stage=%s selected=%s omitted=%s report=%s",
                    report["candidate"].get("name") or "unknown", report["careerStage"], report["selectedEvidenceCount"], report["omittedEvidenceCount"], OUTPUT_PATH)
        return 0
    except Exception as exc:
        LOGGER.error("RESUME_STRATEGY_FAILED type=%s message=%s", type(exc).__name__, str(exc))
        LOGGER.debug("Failure traceback", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
