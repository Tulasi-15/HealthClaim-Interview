"""Optional WHO ICD-10 suggestions and diagnosis terms for policy retrieval."""

import re
import unicodedata
from zipfile import BadZipFile

from backend.reference.reference_data import icd10_codes, search_icd10


_ALIASES = (
    ("cholelithiasis", "gallstones", "gall stones", "gallbladder calculi", "calculi in gall bladder"),
    ("type 2 diabetes mellitus", "type 2 diabetes", "t2dm"),
    ("chronic obstructive pulmonary disease", "copd"),
    ("coronary artery disease", "cad"),
    ("hypertension", "high blood pressure"),
    ("acute myocardial infarction", "heart attack"),
    ("total knee replacement", "total knee arthroplasty", "tkr"),
)


def normalize_diagnosis(text):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold()))


def _primary_phrase(normalized):
    return re.split(r"\s+(?:with|complicated by)\s+", normalized, maxsplit=1)[0]


def diagnosis_terms(text):
    normalized = normalize_diagnosis(text)
    terms = [normalized] if normalized else []
    primary = _primary_phrase(normalized)
    if primary:
        terms.append(primary)
    for aliases in _ALIASES:
        if any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", normalized) for alias in aliases):
            terms.extend(aliases)
    return list(dict.fromkeys(terms))


def _unspecified_candidates(primary, codes):
    """Rank reference labels whose unspecified diagnosis matches the end of the phrase."""
    if re.search(r"\b(?:no|without|suspected|possible|rule out|history of)\b", primary):
        return []
    ranked = []
    for code, label in codes.items():
        name, separator, qualifier = label.rpartition(",")
        if not separator or normalize_diagnosis(qualifier) != "unspecified" or "." not in code:
            continue
        term = normalize_diagnosis(name)
        if term and (primary == term or primary.endswith(" " + term)):
            ranked.append((len(term.split()), {"code": code, "description": label, "term": term}))
    if not ranked:
        return []
    best = max(score for score, _ in ranked)
    return [candidate for score, candidate in ranked if score == best]


def suggest_diagnosis(text):
    terms = diagnosis_terms(text)
    result = {"diagnosis": text, "normalized": terms[0] if terms else "",
              "terms": terms, "candidates": [], "status": "needs_review", "code": None}
    if not terms:
        return result
    try:
        codes = dict(icd10_codes())
        exact = [
            {"code": code, "description": label} for code, label in codes.items()
            if normalize_diagnosis(label) == terms[0] or any(
                terms[0] in aliases and normalize_diagnosis(label) == aliases[0]
                for aliases in _ALIASES
            )
        ]
        direct = search_icd10(terms[0])
        primary = _primary_phrase(terms[0])
        if primary != terms[0] and not any(item["exact_label"] for item in direct):
            direct.extend(search_icd10(primary))
        exact = list({item["code"]: item for item in [
            *exact, *(item for item in direct if item["exact_label"]),
        ]}.values())
        if not exact:
            unspecified = _unspecified_candidates(primary, codes)
            if unspecified:
                result["candidates"] = [
                    {"code": item["code"], "description": item["description"]} for item in unspecified
                ]
                result["terms"] = list(dict.fromkeys([*terms, *(item["term"] for item in unspecified)]))
                if len(unspecified) == 1:
                    result.update(code=unspecified[0]["code"], status="suggested")
                return result
        candidates = {item["code"]: item for item in exact}
        for term in terms:
            for item in search_icd10(term):
                candidates.setdefault(item["code"], item)
        result["candidates"] = list(candidates.values())[:8]
        if len(exact) == 1:
            result["code"] = exact[0]["code"]
            result["status"] = "suggested"
    except (OSError, BadZipFile, KeyError):
        result["status"] = "reference_unavailable"
    return result
