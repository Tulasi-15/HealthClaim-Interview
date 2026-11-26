"""Local, versioned references for claim review."""

from functools import lru_cache
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile


DIRECTORY = Path(__file__).resolve().parents[2] / "healthcare"
IRDAI_DOCUMENTS = {
    "health-2024": {
        "filename": "irdai_health_master_circular_2024.pdf",
        "title": "IRDAI Master Circular on Health Insurance Business",
        "reference": "IRDAI/HLT/CIR/PRO/84/5/2024 · 29 May 2024",
    },
    "expenses-2019": {
        "filename": "irdai_standardization_2019.pdf",
        "title": "IRDAI standard expense lists · Annexure I",
        "reference": "IRDAI/HLT/REG/CIR/176/09/2019 · 27 September 2019",
    },
}


@lru_cache(maxsize=1)
def icd10_codes():
    with ZipFile(DIRECTORY / "icd102019enMeta.zip") as archive:
        tabular = archive.read("icd102019syst_codes.txt").decode("utf-8-sig", errors="replace")
    return tuple(
        (columns[6], columns[8])
        for line in tabular.splitlines()
        if len(columns := line.split(";")) >= 9 and columns[6] and columns[8]
    )


@lru_cache(maxsize=1)
def icd10_inclusions():
    """Read WHO inclusion labels, including labels split across XML fragments."""
    path = DIRECTORY / "icd102019en.xml.zip"
    if not path.is_file():
        return {}
    with ZipFile(path) as archive, archive.open("icd102019en.xml") as file:
        root = ElementTree.parse(file).getroot()
    return {
        entry.attrib["code"]: tuple(
            " ".join(" ".join(label.itertext()).split())
            for label in entry.findall("./Rubric[@kind='inclusion']/Label")
        )
        for entry in root.findall("Class") if "code" in entry.attrib
    }


def search_icd10(query):
    tokens = re.findall(r"[a-z0-9]+", query.casefold())
    compact = "".join(tokens)
    if not compact:
        return []
    ranked = []
    inclusions = icd10_inclusions()
    for code, description in icd10_codes():
        code_key = code.replace(".", "").casefold()
        labels = [description.casefold(), *(label.casefold() for label in inclusions.get(code, ()))]
        match_label = next((label for label in labels if re.findall(r"[a-z0-9]+", label) == tokens), None)
        if compact == code_key:
            score = 0
        elif match_label is not None:
            score = 1
        elif code_key.startswith(compact) and len(compact) >= 2:
            score = 2
        elif any(all(token in label for token in tokens) for label in labels):
            score = 3
        else:
            continue
        ranked.append((score, code, description, match_label))
    return [{"code": code, "description": description, "exact_label": score == 1}
            for score, code, description, _ in sorted(ranked)[:15]]
