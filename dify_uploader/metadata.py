import json
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from pypdf import PdfReader  # type: ignore[import-not-found]
except ImportError:
    PdfReader = None

from dify_uploader.author_extraction import extract_authors_from_pdf
from dify_uploader.baml_author_parser import parse_title_with_baml

# ── PubMed / DOI-based metadata extraction ──────────────────────────


def _extract_doi_from_text(text: str) -> str | None:
    """Extract the first DOI from arbitrary text."""
    doi_pattern = r"\b10\.\d{4,}/[^\s]+\b"
    match = re.search(doi_pattern, text)
    if not match:
        return None
    doi = match.group(0)
    # Strip trailing punctuation
    doi = doi.rstrip(".,;:)")
    return doi


def _extract_doi_from_pdf(filepath: str) -> str | None:
    """Try to extract a DOI from a PDF's first pages."""
    try:
        cmd = ["pdftotext", "-f", "1", "-l", "3", filepath, "-"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        doi = _extract_doi_from_text(result.stdout)
        if doi:
            return doi
    except Exception:
        pass
    return None


def _doi_to_pmid(doi: str, timeout: int = 15) -> str | None:
    """Look up a PubMed ID from a DOI via NCBI E-utilities."""
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={quote(doi)}%5Bdoi%5D&retmode=json"
    )
    req = Request(url=url, headers={"User-Agent": "RmapDifyChatbot/0.4"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if idlist:
            return str(idlist[0])
    except (HTTPError, URLError, json.JSONDecodeError, Exception):
        pass
    return None


def _fetch_pubmed_metadata(pmid: str, timeout: int = 15) -> dict | None:
    """Fetch structured metadata from PubMed via E-utilities efetch (MEDLINE format)."""
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={pmid}&rettype=medline&retmode=text"
    )
    req = Request(url=url, headers={"User-Agent": "RmapDifyChatbot/0.4"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except (HTTPError, URLError, Exception):
        return None

    return _parse_medline(text)


def _parse_medline(text: str) -> dict:
    """Parse PubMed MEDLINE format into {title, authors, year, journal, pmid, doi}."""
    result: dict = {
        "title": "",
        "authors": "",
        "year": "",
        "journal": "",
        "pmid": "",
        "doi": "",
    }

    current_field = None
    authors = []

    for line in text.splitlines():
        # Detect field start (e.g. "TI  - ...", "FAU - ...")
        match = re.match(r"^([A-Z]{2,4})\s*- (.*)", line)
        if match:
            current_field = match.group(1)
            value = match.group(2).strip()
        else:
            # Continuation line (starts with spaces)
            value = line.strip()
            if not value and current_field not in ("AB",):
                current_field = None
                continue

        if current_field == "TI":
            if result["title"]:
                result["title"] += " "
            result["title"] += value
        elif current_field == "FAU":
            authors.append(value)
        elif current_field == "DP":
            # Extract year from "2023 Nov 10" or "2023"
            year_match = re.search(r"\b(19|20)\d{2}\b", value)
            if year_match and not result["year"]:
                result["year"] = year_match.group(0)
        elif current_field == "JT" and not result["journal"]:
            result["journal"] = value
        elif current_field == "TA" and not result["journal"]:
            # Use abbreviated journal title as fallback
            result["journal"] = value
        elif current_field == "PMID":
            if not result["pmid"]:
                result["pmid"] = value.strip()
        elif current_field == "LID":
            doi_match = re.search(r"(10\.\d{4,}/[^\s]+)", value)
            if doi_match and not result["doi"]:
                result["doi"] = doi_match.group(1).rstrip(".")

    if authors:
        result["authors"] = ", ".join(authors)

    return result


def extract_metadata_pubmed(filepath: str) -> dict | None:
    """Extract metadata from a PDF via DOI → PubMed lookup.

    Returns a dict with title, authors, year, journal, pmid, doi
    or None if no DOI/PubMed record was found.
    """
    doi = _extract_doi_from_pdf(filepath)
    if not doi:
        return None

    # Rate-limit: be polite to NCBI
    time.sleep(0.35)

    pmid = _doi_to_pmid(doi)
    if not pmid:
        return None

    time.sleep(0.35)

    return _fetch_pubmed_metadata(pmid)


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
    # ── 1. PubMed via DOI (authoritative, no LLM needed) ──────────────
    if filepath and filepath.lower().endswith(".pdf"):
        pubmed = extract_metadata_pubmed(filepath)
        if pubmed and pubmed.get("title"):
            return {
                "title": pubmed["title"],
                "authors": pubmed["authors"] or "Unknown",
                "year": pubmed["year"] or "Unknown",
                "journal": pubmed["journal"] or "Unknown",
                "pmid": pubmed.get("pmid", ""),
                "doi": pubmed.get("doi", ""),
            }

    # ── 2. Fallback: filename parsing + LLM ───────────────────────────
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
