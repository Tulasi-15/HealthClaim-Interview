"""Build and search page-grounded passages from uploaded policy text."""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import get_close_matches
from itertools import zip_longest

from backend.policies.policy_room_limit import RoomLimit
from backend.policies.policy_waiting_period import WaitingPeriodRule


_TOKEN = re.compile(r"[^\W_]+")
_PAGE_MARKER = re.compile(r"page \d+(?: of \d+)?", re.I)
_SECTION_TITLE = re.compile(r"^\d+(?:\.\d+)*\.\s+")
_NUMBERED_CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+)\.?(?:\s|$)")
_MAIN_HEADING = re.compile(r"^(\d{1,2})\.\s+([A-Z][A-Z &/-]+)$")
_SUBCLAUSE = re.compile(r"^([a-z])\.\s+", re.I)
_NUMBERED_GROUP = re.compile(r"^\(([ivxlcdm]+)\)\s+", re.I)
_COVERAGE_INTENT = re.compile(r"\b(?:covered|cover|coverage|pay|reimburs\w*)\b", re.I)
_PERCENT_QUESTION = re.compile(r"\bpercent(?:age)?\b|%", re.I)
_PERCENT_VALUE = re.compile(r"\d\s*%")
_PED_WAITING = re.compile(
    r"pre-existing diseases?.{0,450}?(?:shall be )?excluded until the expiry of "
    r"(\d{1,2}) months? of continuous coverage",
    re.I | re.S,
)
_SPECIFIC_WAITING_HEADING = re.compile(r"specified disease\s*/\s*procedure waiting", re.I)
_WAITING_DURATION = re.compile(r"\b(\d{1,2})\s+months?\s+waiting period\b", re.I)
_WAITING_ITEM = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.*)$")
_PRE_HOSPITALIZATION_PERIOD = re.compile(
    r"pre[-\s]?hospitalization\b.{0,350}?for a fixed period of (\d{1,3}) days?"
    r".{0,120}?prior to.{0,120}?(?:admissible )?hospitalization\b",
    re.I | re.S,
)
_POST_HOSPITALIZATION_PERIOD = re.compile(
    r"post[-\s]?hospitalization\b.{0,350}?for a fixed period of (\d{1,3}) days?"
    r".{0,120}?from the date of discharge from the hospital",
    re.I | re.S,
)
_ANNEXURE_LIST_HEADING = re.compile(r"^\s*List\s+([IVXLCDM]+)\s*[–-]\s*(.+?)\s*$", re.I)
_STOPWORDS = set(
    "a about an and am are as at be can could cover covered coverage did do does for from "
    "have how i if in is it me my of on or pay policy should that the this to under "
    "was were what when where which who will with would you your".split()
)
_TERM_ALIASES = {"accident": "injury", "accidents": "injury", "accidental": "injury", "injuries": "injury"}


@dataclass(frozen=True)
class PolicyPassage:
    citation: str
    text: str
    search_context: str = ""
    room_limit: bool = False
    recorded_estimate: bool = False
    document_name: str = ""
    estimate_total: bool = False
    waiting_group: tuple[int, int, int] | None = None
    hospital_document: int | None = None


def build_hospital_passages(pages, filename, document, first_page=1, last_page=None):
    return [
        PolicyPassage(f"Hospital PDF page {number}", passage.text, passage.search_context,
                      document_name=filename, hospital_document=document)
        for number, text in enumerate(pages[first_page - 1:last_page], first_page)
        for passage in _page_passages(text.splitlines(), number)
    ]


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return [
        word for word in _TOKEN.findall(text.casefold())
        if len(word) > 1 and word not in _STOPWORDS
    ]


def build_policy_passages(
    pages: list[str], room_limit: RoomLimit | None, waiting_rules: list[WaitingPeriodRule]
) -> list[PolicyPassage]:
    """Keep original page numbers and split policy body into short evidence passages."""
    repeated = Counter()
    for page in pages:
        lines = [" ".join(raw.casefold().split()).rstrip(".") for raw in page.splitlines() if raw.strip()]
        repeated.update(line for line in set(lines[:4] + lines[-3:]) if len(line.split()) >= 3)
    passages = []
    active_list_heading = ""
    for number, page in enumerate(pages, 1):
        lines = [line.strip() for line in page.splitlines()]
        list_heading = next(
            (_ANNEXURE_LIST_HEADING.match(line) for line in lines if _ANNEXURE_LIST_HEADING.match(line)),
            None,
        )
        if list_heading:
            active_list_heading = f"List {list_heading.group(1).upper()}: {list_heading.group(2)}"
        if number == 1:
            first_section = next(
                (index for index, line in enumerate(lines) if _SECTION_TITLE.match(line)), None
            )
            front_lines = [
                line for line in lines[:first_section] if line and not _PAGE_MARKER.fullmatch(line)
            ]
            if front_lines:
                front = " ".join(front_lines if first_section is not None else front_lines[:6])
                passages.append(PolicyPassage("PDF page 1", front, "policy document name title insurer"))
            if first_section is not None:
                lines = lines[first_section:]

        clean = (
            line for line in lines
            if not _PAGE_MARKER.fullmatch(line)
            and repeated[" ".join(line.casefold().split()).rstrip(".")] < 3
        )
        page_passages = _page_passages(clean, number)
        if active_list_heading:
            page_passages = [
                PolicyPassage(
                    citation=passage.citation,
                    text=passage.text,
                    search_context=f"{active_list_heading}. {passage.search_context}".strip(),
                    room_limit=passage.room_limit,
                    recorded_estimate=passage.recorded_estimate,
                    document_name=passage.document_name,
                    estimate_total=passage.estimate_total,
                )
                for passage in page_passages
            ]
        passages.extend(page_passages)

    if room_limit is not None:
        passages.append(PolicyPassage(
            f"Clause 4.1(a) · PDF page {room_limit.page}", room_limit.excerpt,
            "standard daily room limit", room_limit=True,
        ))
    rule_groups = defaultdict(list)
    for rule in waiting_rules:
        page = str(rule.first_page)
        if rule.last_page != rule.first_page:
            page += f"–{rule.last_page}"
        passages.append(PolicyPassage(
            f"Clause {rule.clause} · PDF page {page}", rule.condition,
            f"{rule.months}-month specific waiting period",
        ))
        rule_groups[(rule.group, rule.months)].append(rule)
    for (group, months), rules in rule_groups.items():
        if len(rules) < 2 or sum(len(rule.condition.split()) for rule in rules) > 250:
            continue
        first, last = rules[0].first_page, rules[-1].last_page
        page = str(first) if first == last else f"{first}–{last}"
        passages.append(PolicyPassage(
            f"Clause 6.2({group}) · PDF page {page}",
            "\n".join(f"{rule.item}. {rule.condition}" for rule in rules),
            f"{months}-month specific waiting period list",
        ))
    passages.extend(_alternate_waiting_passages(pages))
    passages.extend(_hospitalization_period_passages(pages))
    return passages


def _hospitalization_period_passages(pages: list[str]) -> list[PolicyPassage]:
    """Keep hospitalization benefit headings attached to their stated day limits."""
    additions = []
    for page_number, page in enumerate(pages, 1):
        normalized = " ".join(page.replace("ﬁ", "fi").split())
        for pattern, context in (
            (
                _PRE_HOSPITALIZATION_PERIOD,
                "pre-hospitalization medical expenses before admission",
            ),
            (
                _POST_HOSPITALIZATION_PERIOD,
                "post-hospitalization medical expenses after discharge",
            ),
        ):
            match = pattern.search(normalized)
            if match:
                days = match.group(1)
                additions.append(PolicyPassage(
                    f"PDF page {page_number}", match.group(0),
                    f"{context}; {days} days covered under the policy",
                ))
    return additions


def grouped_waiting_rules(pages: list[str]) -> list[WaitingPeriodRule]:
    rules = []
    for passage in _alternate_waiting_passages(pages):
        if passage.waiting_group:
            months, item, page = passage.waiting_group
            rules.append(WaitingPeriodRule(
                str(months), item, months, passage.text, page, page,
                f"{months}-month waiting period, item {item} (page {page})",
            ))
    return rules


def _alternate_waiting_passages(pages: list[str]) -> list[PolicyPassage]:
    """Extract explicit waiting-period evidence from layouts without the standard clause format."""
    additions = []
    for page_number, page in enumerate(pages, 1):
        normalized_page = page.replace("ﬁ", "fi")
        collapsed = " ".join(normalized_page.split())
        collapsed = re.sub(r"(?<=\w)-\s+(?=\w)", "-", collapsed)
        ped = _PED_WAITING.search(collapsed)
        if ped:
            additions.append(PolicyPassage(
                f"PDF page {page_number}", ped.group(0),
                f"pre-existing disease waiting period {ped.group(1)} months continuous coverage",
            ))

        lines = normalized_page.splitlines()
        if not any(_SPECIFIC_WAITING_HEADING.search(line) for line in lines):
            continue

        in_list = False
        duration = ""
        basis = ""
        item_number = None
        item_lines = []

        def save_item():
            if item_number is not None and item_lines:
                condition = " ".join(" ".join(item_lines).split())
                context = f"{basis} {duration}-month specific waiting period item {item_number}"
                additions.append(PolicyPassage(
                    f"PDF page {page_number}", condition, context.strip(),
                    waiting_group=(int(duration), int(item_number), page_number) if duration else None,
                ))

        for line in lines:
            if _SPECIFIC_WAITING_HEADING.search(line):
                in_list = True
                basis = " ".join(line.split())
                continue
            if not in_list:
                continue
            if re.search(r"\b30\s*[- ]day waiting period\b", line, re.I):
                save_item()
                break
            if "list of specific diseases/procedures" in line.casefold():
                basis += " " + " ".join(line.split())
                continue
            duration_match = _WAITING_DURATION.search(line)
            if duration_match:
                save_item()
                item_number, item_lines = None, []
                duration = duration_match.group(1)
                basis = f"{duration} months waiting period; {basis}"
                continue
            item_match = _WAITING_ITEM.match(line)
            if item_match:
                save_item()
                item_number = item_match.group(1)
                item_lines = [item_match.group(2)] if item_match.group(2).strip() else []
            elif item_number is not None and line.strip():
                item_lines.append(line.strip())
            elif line.strip():
                basis += " " + " ".join(line.split())
        else:
            save_item()
    return additions


def _page_passages(lines, page: int) -> list[PolicyPassage]:
    passages = []
    clause = None
    subclause = None
    heading_context = ""
    paragraph = []
    for line in [*lines, ""]:
        heading = _NUMBERED_CLAUSE.match(line) or _MAIN_HEADING.fullmatch(line)
        group = _NUMBERED_GROUP.match(line) if clause and not heading else None
        letter = _SUBCLAUSE.match(line) if clause and not heading and not group else None
        if letter and letter[1].lower() != (chr(ord(subclause) + 1) if subclause and len(subclause) == 1 else "a"):
            letter = None
        if paragraph and (heading or group or letter or not line):
            number = f"{clause}({subclause})" if subclause else clause
            citation = f"Clause {number} · PDF page {page}" if number else f"PDF page {page}"
            words = " ".join(paragraph).split()
            for start in range(0, len(words), 100):
                passages.append(PolicyPassage(citation, " ".join(words[start:start + 120]), heading_context))
            paragraph = []
        if heading:
            clause = heading[1]
            subclause = None
            heading_context = line if len(line.split()) <= 12 else ""
        elif group:
            subclause = group[1].lower()
            heading_context = line
        elif letter:
            subclause = letter[1].lower()
        if line:
            paragraph.append(line)
    return passages


def retrieve_policy_passages(question: str, passages: list[PolicyPassage], limit: int = 7) -> list[PolicyPassage]:
    """Rank lexical matches and keep evidence for distinct terms in the question."""
    documents = [set(_tokens(f"{entry.search_context} {entry.text}")) for entry in passages]
    for document in documents:
        document.update(_TERM_ALIASES[word] for word in document.copy() if word in _TERM_ALIASES)
    frequencies = Counter(word for document in documents for word in document)
    vocabulary = sorted(frequencies.keys() | _TERM_ALIASES.keys())
    query = {}
    for word in dict.fromkeys(_tokens(question)):
        match = word
        if match not in vocabulary and len(word) >= 5:
            nearby = get_close_matches(word, vocabulary, n=1, cutoff=0.84)
            if nearby:
                match = nearby[0]
        for term in dict.fromkeys((match, _TERM_ALIASES.get(match, match))):
            if term in frequencies:
                query[term] = math.log1p(len(documents) / frequencies[term])
    ranked = sorted(
        (
            (sum(weight for word, weight in query.items() if word in document), index)
            for index, document in enumerate(documents)
        ),
        key=lambda result: (
            -result[0],
            -len(set(_tokens(passages[result[1]].search_context)) & query.keys()),
            not passages[result[1]].room_limit,
            result[1],
        ),
    )
    ranked = [(score, index) for score, index in ranked if score > 0]
    if not ranked:
        return []
    if _PERCENT_QUESTION.search(question):
        with_percentages = [
            (score, index) for score, index in ranked if _PERCENT_VALUE.search(passages[index].text)
        ]
        if with_percentages:
            ranked = with_percentages
    minimum = ranked[0][0] * 0.75
    matching_indices = [index for score, index in ranked if score >= minimum]
    # Reserve a few slots for each term so a word like "road" cannot fill the list with addresses.
    per_term = [[index for index in matching_indices if term in documents[index]][:3] for term in query]
    coverage = [index for group in zip_longest(*per_term) for index in group if index is not None]
    grouped = next((
        index for index in matching_indices
        if "waiting period list" in passages[index].search_context
        and {"waiting", "period"} <= query.keys()
    ), None)
    priorities = [grouped] if grouped is not None else []
    if _COVERAGE_INTENT.search(question):
        operative = next((
            i for i, passage in enumerate(passages)
            if "operative clause" in passage.search_context.casefold() and len(passage.text.split()) >= 25
        ), None)
        if operative is not None:
            priorities.append(operative)
    chosen = dict.fromkeys([*matching_indices[:1], *priorities, *coverage, *matching_indices])
    return [passages[index] for index in list(chosen)[:limit]]


def fuse_policy_passages(
    keyword_passages: list[PolicyPassage],
    semantic_passages: list[PolicyPassage],
    *,
    limit: int = 12,
) -> list[PolicyPassage]:
    """Rank both result lists with reciprocal-rank fusion without truncating either source."""
    scores = defaultdict(float)
    first_seen = {}
    for source_weight, results in ((0.55, keyword_passages), (0.45, semantic_passages)):
        for rank, passage in enumerate(results):
            scores[passage] += source_weight / (60 + rank + 1)
            first_seen.setdefault(passage, len(first_seen))
    return sorted(scores, key=lambda passage: (-scores[passage], first_seen[passage]))[:limit]
