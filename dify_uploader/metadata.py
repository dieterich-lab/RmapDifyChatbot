import re
import subprocess

try:
    from pypdf import PdfReader  # type: ignore[import-not-found]
except ImportError:
    PdfReader = None

from dify_uploader.author_extraction import extract_authors_from_pdf
from dify_uploader.baml_author_parser import parse_title_with_baml


def _normalize_title(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" -_,;:")
    return value


def _title_quality_score(title: str) -> int:
    value = _normalize_title(title)
    if not value:
        return 1000

    score = 0
    lower = value.lower()

    if len(value) < 12:
        score += 60
    if ".pdf" in lower:
        score += 120
    if value.count(",") >= 2:
        score += 40
    if re.search(r"\b(19|20)\d{2}\b", value):
        score += 25

    noisy_markers = {
        "open access",
        "research article",
        "abstract",
        "creative commons",
        "doi",
        "received",
        "accepted",
    }
    for marker in noisy_markers:
        if marker in lower:
            score += 30

    return score


def _extract_header_text(filepath: str, reader=None) -> str:
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


def _extract_title_from_pdf(filepath: str, fallback_title: str) -> str:
    baseline = _normalize_title(fallback_title)
    header_text = ""
    meta_title = ""

    reader = None
    if PdfReader is not None:
        try:
            reader = PdfReader(filepath)
            metadata = reader.metadata or {}
            meta_title = _normalize_title(
                str(metadata.get("/Title") or metadata.get("title") or "")
            )
        except Exception:
            meta_title = ""

    header_text = _extract_header_text(filepath, reader=reader)
    llm_title = _normalize_title(parse_title_with_baml(header_text) or "")

    candidates = [baseline]
    if meta_title:
        candidates.append(meta_title)
    if llm_title:
        candidates.append(llm_title)

    best = baseline
    best_score = _title_quality_score(best)
    for candidate in candidates[1:]:
        score = _title_quality_score(candidate)
        if score < best_score:
            best = candidate
            best_score = score
    return best


def extract_metadata(
    filename: str, filepath: str | None = None, use_hybrid_pipeline: bool = True
) -> dict:
    clean_name = filename.replace(".pdf", "").replace(".PDF", "").strip()
    parts = [p.strip() for p in clean_name.split(",")]

    metadata = {
        "title": clean_name,
        "authors": "Unknown",
        "year": "Unknown",
        "journal": "Unknown",
    }

    if len(parts) >= 3:
        metadata["journal"] = str(parts[-1]).strip()
        year_match = re.search(r"\b(19|20)\d{2}\b", parts[-2])
        if year_match:
            metadata["year"] = str(year_match.group(0))
            metadata["authors"] = str(", ".join(parts[:-2]))
        else:
            metadata["year"] = str(parts[-2]).strip()
            metadata["authors"] = str(", ".join(parts[:-2]))

    if filepath and filepath.lower().endswith(".pdf") and use_hybrid_pipeline:
        metadata["title"] = _extract_title_from_pdf(filepath, metadata["title"])
        pdf_authors = extract_authors_from_pdf(filepath)
        if pdf_authors:
            metadata["authors"] = pdf_authors

    return metadata
