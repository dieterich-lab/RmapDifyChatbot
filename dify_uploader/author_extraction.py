import re
import subprocess

from dify_uploader.baml_author_parser import parse_authors_with_baml

try:
    from pypdf import PdfReader  # type: ignore[import-not-found]
except ImportError:
    PdfReader = None


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        norm = key.lower()
        if norm in seen:
            continue
        seen.add(norm)
        result.append(key)
    return result


_ORG_KEYWORDS = {
    "academy",
    "center",
    "centre",
    "college",
    "department",
    "faculty",
    "hospital",
    "institute",
    "laboratory",
    "lab",
    "school",
    "science",
    "sciences",
    "university",
    "research",
    "cardiology",
    "medicine",
    "medical",
    "clinic",
    "biomedical",
}

_NON_NAME_TOKENS = {
    "academy",
    "biology",
    "biotechnology",
    "campus",
    "cardiology",
    "cell",
    "centre",
    "center",
    "chemistry",
    "clinic",
    "clinical",
    "college",
    "computational",
    "department",
    "engineering",
    "faculty",
    "feld",
    "genetics",
    "gmbh",
    "group",
    "heidelberg",
    "hospital",
    "im",
    "institute",
    "integrative",
    "laboratory",
    "lab",
    "medicine",
    "medical",
    "molecular",
    "partner",
    "protein",
    "research",
    "school",
    "science",
    "sciences",
    "site",
    "target",
    "therapeutics",
    "university",
}

_LOWERCASE_NAME_PARTICLES = {
    "al",
    "bin",
    "da",
    "das",
    "de",
    "del",
    "della",
    "den",
    "der",
    "di",
    "do",
    "dos",
    "du",
    "el",
    "ibn",
    "la",
    "le",
    "van",
    "von",
}


def _normalize_initials_token(token: str) -> str | None:
    compact = str(token or "").strip()
    if not compact:
        return None

    letters_only = "".join(char for char in compact if char.isalpha())
    if not letters_only:
        return None

    # Treat as initials only when dots are present (e.g. L.A.) or for single-letter initials.
    if "." not in compact and len(letters_only) != 1:
        return None

    if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ.]+", compact) and len(letters_only) <= 4:
        return ".".join(char.upper() for char in letters_only) + "."
    return None


def _capitalize_name_fragment(fragment: str) -> str:
    if not fragment:
        return fragment
    return fragment[0].upper() + fragment[1:].lower()


def _normalize_name_segment(segment: str, is_first_token: bool) -> str:
    initials = _normalize_initials_token(segment)
    if initials is not None:
        return initials

    should_normalize = segment.isupper() or segment.islower()
    if not should_normalize:
        return segment

    lowered = segment.lower()
    if not is_first_token and lowered in _LOWERCASE_NAME_PARTICLES:
        return lowered

    apostrophe_parts = lowered.split("'")
    return "'".join(_capitalize_name_fragment(part) for part in apostrophe_parts)


def _normalize_author_casing(value: str) -> str:
    tokens = value.split()
    normalized_tokens: list[str] = []

    for token_index, token in enumerate(tokens):
        hyphen_parts = token.split("-")
        normalized_parts = [
            _normalize_name_segment(part, is_first_token=(token_index == 0))
            for part in hyphen_parts
        ]
        normalized_tokens.append("-".join(normalized_parts))

    return " ".join(normalized_tokens)


def _normalize_author_piece(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ,;:|")
    text = _normalize_author_casing(text)
    return text


def _looks_like_organization(value: str) -> bool:
    lowered = value.lower()
    return any(keyword in lowered for keyword in _ORG_KEYWORDS)


def _is_plausible_person_name(value: str) -> bool:
    text = _normalize_author_piece(value)
    if not text:
        return False
    if any(char.isdigit() for char in text):
        return False
    if _looks_like_organization(text):
        return False

    tokens = text.split()
    if len(tokens) < 2 or len(tokens) > 7:
        return False

    lowered_tokens = {token.strip(".,").lower() for token in tokens}
    if lowered_tokens & _NON_NAME_TOKENS:
        return False

    valid_tokens = 0
    for token in tokens:
        token_clean = token.strip(".,")
        if not token_clean:
            continue
        if re.fullmatch(r"[A-ZÀ-ÖØ-Ý]\.?", token_clean):
            valid_tokens += 1
            continue
        if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'\-\.]{2,}", token_clean):
            valid_tokens += 1
            continue
        return False

    # At least two name-like tokens should remain after cleanup.
    return valid_tokens >= 2


def _filter_author_names(candidates: list[str]) -> list[str]:
    cleaned = []
    for candidate in candidates:
        value = _normalize_author_piece(candidate)
        if not value:
            continue
        if _is_plausible_person_name(value):
            cleaned.append(value)
    return _unique_preserve_order(cleaned)


def _extract_author_names_from_text(text: str) -> list[str]:
    name_pattern = re.compile(
        r"\b[A-Z][a-zA-Z'\-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'\-]+){1,2}\b"
    )
    stop_words = {
        "abstract",
        "introduction",
        "keywords",
        "references",
        "copyright",
        "open",
        "access",
        "article",
        "review",
        "journal",
        "chemmedchem",
    }

    names = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if "abstract" in line.lower() or "introduction" in line.lower():
            break
        if len(line) > 180:
            continue

        candidates = name_pattern.findall(line)
        for candidate in candidates:
            words = candidate.split()
            if len(words) < 2:
                continue
            if any(w.lower() in stop_words for w in words):
                continue
            names.append(candidate.strip())

    return _filter_author_names(names)


def _extract_authors_with_pdftotext(filepath: str) -> list[str]:
    try:
        cmd = ["pdftotext", "-f", "1", "-l", "1", filepath, "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        page_text = result.stdout
    except Exception:
        return []

    lines = [" ".join(line.split()) for line in page_text.splitlines() if line.strip()]

    author_block = ""
    start_idx = None
    for i, line in enumerate(lines):
        if line.count(",") >= 2 and re.search(r"\[[a-z]\]", line):
            start_idx = i
            break

    if start_idx is not None:
        block_lines = []
        for line in lines[start_idx : start_idx + 4]:
            block_lines.append(line)
            if not re.search(r"\[[a-z]\]", line) and " and " not in line.lower():
                break
        author_block = " ".join(block_lines)

    if not author_block:
        return []

    first_name_match = re.search(
        r"[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ'\-]+\s+[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ'\-]+",
        author_block,
    )
    if first_name_match:
        author_block = author_block[first_name_match.start() :]

    author_block = re.split(
        r"\b(The continuous|Introduction|Abstract)\b", author_block, maxsplit=1
    )[0]

    cleaned = re.sub(r"\[[a-z]\]", "", author_block)
    cleaned = cleaned.replace("*", " ").replace("+", " ")
    cleaned = re.sub(r"\s+and\s+", ", ", cleaned, flags=re.IGNORECASE)
    parts = [p.strip(" ,") for p in cleaned.split(",") if p.strip(" ,")]

    names = []
    for part in parts:
        words = part.split()
        if len(words) < 2:
            continue
        if not any(ch.isalpha() for ch in part):
            continue
        lowered = part.lower()
        if any(
            tag in lowered
            for tag in ["research article", "doi", "introduction", "abstract"]
        ):
            continue
        names.append(part)

    return _filter_author_names(names)


def _extract_header_text(filepath: str, reader=None) -> str:
    # Prefer pdftotext first page because it usually preserves visible header order.
    try:
        cmd = ["pdftotext", "-f", "1", "-l", "1", filepath, "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        text = (result.stdout or "").strip()
        if text:
            return text
    except Exception:
        pass

    if reader is not None:
        try:
            text = (reader.pages[0].extract_text() or "").strip()
            if text:
                return text
        except Exception:
            pass
    return ""


def _is_low_confidence_author_result(names: list[str]) -> bool:
    if not names:
        return True
    if len(names) == 1:
        return True
    if len(names) > 20:
        return True

    joined = " ".join(names).lower()
    noisy_markers = {
        "received",
        "revised",
        "editorial decision",
        "accepted",
        "direct submission",
        "creative commons",
        "copyright",
        "doi",
    }
    if any(marker in joined for marker in noisy_markers):
        return True

    if _looks_like_organization(joined):
        return True

    return False


def _author_quality_score(names: list[str]) -> int:
    if not names:
        return 1000

    score = 0
    if len(names) == 1:
        score += 60
    if len(names) > 20:
        score += 50 + (len(names) - 20)

    joined = " ".join(names).lower()
    noisy_markers = {
        "received",
        "revised",
        "editorial decision",
        "accepted",
        "direct submission",
        "creative commons",
        "copyright",
        "doi",
    }
    for marker in noisy_markers:
        if marker in joined:
            score += 20

    if _looks_like_organization(joined):
        score += 40

    non_person = sum(1 for name in names if not _is_plausible_person_name(name))
    score += non_person * 10
    return score


def _prefer_better_candidate(regex_names: list[str], llm_names: list[str]) -> list[str]:
    if not regex_names:
        return llm_names
    if not llm_names:
        return regex_names

    regex_score = _author_quality_score(regex_names)
    llm_score = _author_quality_score(llm_names)

    if llm_score < regex_score:
        return llm_names
    if llm_score > regex_score:
        return regex_names

    # Tie-breaker: prefer the richer candidate when quality is equal.
    if len(llm_names) > len(regex_names):
        return llm_names
    return regex_names


def extract_authors_from_pdf(filepath: str) -> str | None:
    header_text = ""

    if PdfReader is None:
        pdf_text_names = _extract_authors_with_pdftotext(filepath)
        header_text = _extract_header_text(filepath)
        if pdf_text_names and not _is_low_confidence_author_result(pdf_text_names):
            return ", ".join(pdf_text_names)

        llm_names = _filter_author_names(parse_authors_with_baml(header_text))
        best_names = _prefer_better_candidate(pdf_text_names, llm_names)
        if best_names:
            return ", ".join(best_names)
        return None

    try:
        reader = PdfReader(filepath)
    except Exception as exc:
        print(f"⚠️ Konnte PDF nicht lesen fuer Autor-Extraktion: {exc}")
        return None

    meta_author = None
    try:
        metadata = reader.metadata or {}
        meta_author = metadata.get("/Author") or metadata.get("author")
    except Exception:
        meta_author = None

    if meta_author:
        raw = str(meta_author).replace("\n", " ").strip()
        parts = re.split(r";|\band\b|\|", raw, flags=re.IGNORECASE)
        cleaned = _filter_author_names([p.strip(" ,") for p in parts if p.strip(" ,")])
        if cleaned and not _is_low_confidence_author_result(cleaned):
            return ", ".join(cleaned)

    pdf_text_names = _extract_authors_with_pdftotext(filepath)
    if pdf_text_names and not _is_low_confidence_author_result(pdf_text_names):
        return ", ".join(pdf_text_names)

    regex_candidate = cleaned if meta_author else []
    regex_candidate = _prefer_better_candidate(regex_candidate, pdf_text_names)

    header_text = _extract_header_text(filepath, reader=reader)
    llm_names = _filter_author_names(parse_authors_with_baml(header_text))
    best_names = _prefer_better_candidate(regex_candidate, llm_names)
    if best_names and not _is_low_confidence_author_result(best_names):
        return ", ".join(best_names)

    text_chunks = []
    for page in reader.pages[:2]:
        try:
            text_chunks.append(page.extract_text() or "")
        except Exception:
            continue

    text = "\n".join(text_chunks)
    names = _extract_author_names_from_text(text)
    best_names = _prefer_better_candidate(best_names, names)
    if best_names and not _is_low_confidence_author_result(best_names):
        return ", ".join(best_names)

    if not llm_names and text:
        llm_names = _filter_author_names(parse_authors_with_baml(text[:6000]))
    best_names = _prefer_better_candidate(best_names, llm_names)
    if best_names:
        return ", ".join(best_names)

    return None
