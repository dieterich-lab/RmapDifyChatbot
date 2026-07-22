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
from dify_uploader.baml_author_parser import (
    parse_authors_with_baml,
    parse_title_with_baml,
)

# ── PubMed / DOI-based metadata extraction ──────────────────────────


def _extract_doi_from_text(text: str) -> str | None:
    """Extract the best DOI from arbitrary text.

    Returns the longest match to avoid truncated DOIs (e.g. '10.1073/pnas.'
    vs '10.1073/pnas.2312330121') that result from PDF line breaks.
    """
    doi_pattern = r"\b10\.\d{4,}/[^\s]+\b"
    matches = re.findall(doi_pattern, text)
    if not matches:
        return None
    # Strip trailing punctuation from each match
    cleaned = [m.rstrip(".,;:") for m in matches]
    # Filter out likely truncated DOIs (too short, e.g. just '10.1073/pnas.')
    # Valid DOIs have a suffix after the prefix
    valid = [m for m in cleaned if len(m.split("/")[-1]) >= 3]
    if not valid:
        # Fall back to longest match if all look truncated
        valid = cleaned
    # Prefer the longest match (truncated DOIs are shorter)
    doi = max(valid, key=len)
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


# ── CrossRef / DOI-based metadata extraction (fallback for non-PubMed DOIs) ──


def _fetch_crossref_metadata(doi: str, timeout: int = 15) -> dict | None:
    """Fetch metadata from CrossRef API when PubMed has no entry for this DOI."""
    url = f"https://api.crossref.org/works/{quote(doi)}"
    req = Request(url=url, headers={"User-Agent": "RmapDifyChatbot/0.4"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError, Exception):
        return None

    msg = data.get("message", {})
    if not msg:
        return None

    # Title
    title_list = msg.get("title") or []
    title = str(title_list[0]).strip() if title_list else ""

    # Authors: CrossRef gives "given" + "family"; format as "Family Given"
    authors = []
    for author in msg.get("author") or []:
        family = str(author.get("family", "")).strip()
        given = str(author.get("given", "")).strip()
        if family and given:
            authors.append(f"{family} {given}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)

    # Year: from created or published date-parts
    year = ""
    date_parts = (
        msg.get("published-print", {}).get("date-parts")
        or msg.get("published-online", {}).get("date-parts")
        or msg.get("created", {}).get("date-parts")
    )
    if date_parts and date_parts[0]:
        year = str(date_parts[0][0])

    # Journal: container-title or short-container-title
    journal_list = msg.get("container-title") or msg.get("short-container-title") or []
    journal = str(journal_list[0]).strip() if journal_list else ""

    if not title:
        return None

    return {
        "title": title,
        "authors": ", ".join(authors) if authors else "Unknown",
        "year": year or "Unknown",
        "journal": journal or "Unknown",
        "pmid": "",
        "doi": doi,
    }


def extract_metadata_crossref(filepath: str) -> dict | None:
    """Extract metadata from a PDF via DOI → CrossRef lookup.

    Returns a dict with title, authors, year, journal, doi
    or None if no DOI was found or CrossRef has no entry.
    """
    doi = _extract_doi_from_pdf(filepath)
    if not doi:
        return None

    # Rate-limit: be polite
    time.sleep(0.2)

    return _fetch_crossref_metadata(doi)


# ── LLM-based metadata extraction from PDF header (fallback for no-DOI papers) ──


def _extract_year_from_text(text: str) -> str:
    """Extract a plausible publication year from header/footer text."""
    years = re.findall(r"\b((?:19|20)\d{2})\b", text)
    if not years:
        return ""
    # Take most common year in 2000-2026 range (publication year, not copyright spans)
    from collections import Counter

    counts = Counter(years)
    for year, _ in counts.most_common():
        y = int(year)
        if 2000 <= y <= 2026:
            return year
    # Fallback: most recent year found
    return str(max(int(y) for y in years))


def _extract_journal_from_header(text: str) -> str:
    """Try to identify journal name from PDF header text."""
    # Common journal patterns in header text
    journal_patterns = [
        r"(?:Nucleic Acids Research|Nucleic Acids Res)",
        r"(?:Nature Communications|Nat Commun|Nat\. Commun\.?)",
        r"(?:Nature Structural)[\s&]+(?:Molecular Biology)",
        r"(?:Molecular Cell|Mol Cell)",
        r"(?:Cell Reports|Cell Rep)",
        r"(?:Genome Biology|Genome Biol)",
        r"(?:Genome Research|Genome Res)",
        r"(?:PNAS|Proceedings of the National Academy)",
        r"(?:EMBO Journal|EMBO J|The EMBO Journal)",
        r"(?:EMBO Reports|EMBO Rep)",
        r"(?:Science Advances|Sci Adv)",
        r"(?:Nature Reviews)[\s.]+(?:Genetics|Molecular)",
        r"(?:Nature)[\s.]+(?:Methods|Biotechnology)",
        r"(?:Bioinformatics)",
        r"(?:RNA|RNA Biology|RNA Biol)",
        r"(?:Journal of Biological Chemistry|J Biol Chem)",
        r"(?:Journal of Molecular Biology|J Mol Biol)",
        r"(?:iScience)",
        r"(?:eLife)",
        r"(?:BioEssays)",
        r"(?:Methods)",
        r"(?:Angewandte Chemie|Angew Chem Int Ed)",
        r"(?:ACS Chemical Biology|ACS Chem Biol)",
        r"(?:ACS Medicinal Chemistry Letters|ACS Med Chem Lett)",
        r"(?:Journal of Medicinal Chemistry|J Med Chem)",
        r"(?:ACS Pharmacology)[\s&]+(?:Translational Science)",
        r"(?:RSC Chemical Biology|RSC Chem Biol)",
        r"(?:Chemical Science|Chem Sci)",
        r"(?:ChemMedChem)",
        r"(?:ChemBioChem)",
        r"(?:Chemistry)[\s-]+(?:A European Journal)",
        r"(?:Communications Chemistry|Commun Chem)",
        r"(?:WIREs RNA|Wiley Interdisciplinary Reviews)[\s.:]+RNA",
        r"(?:Accounts of Chemical Research|Acc Chem Res|Acc\. Chem\. Res\.?)",
        r"(?:Current Opinion)[\s.]+(?:in[\s.]+)?(?:Genetics|Structural Biology)",
        r"(?:Current Opinion in Genetics)[\s&]+Development",
        r"(?:Signal Transduction)[\s&]+(?:Targeted Therapy)",
        r"(?:Experimental)[\s&]+(?:Molecular Medicine)",
        r"(?:Molecular Cancer|Mol Cancer)",
        r"(?:Genetics in Medicine|Genet Med)",
        r"(?:Frontiers)[\s.]+(?:in[\s.]+)?(?:Cell)[\s.]+(?:and[\s.]+)?(?:Developmental Biology)",
        r"(?:Journal of Proteome Research|J Proteome Res)",
        r"(?:Journal of Bacteriology|J Bacteriol)",
        r"(?:BMC Bioinformatics)",
        r"(?:International Journal of Molecular Sciences|Int J Mol Sci)",
        r"(?:Journal of Cell Biology|J Cell Biol)",
        r"(?:Computational and Structural Biotechnology Journal|Comput Struct Biotechnol J)",
        r"(?:Drug Discovery Today|Drug Discov Today)",
        r"(?:Rapid Communications in Mass Spectrometry|Rapid Comm Mass Spectrom)",
        r"(?:HardwareX)",
        r"(?:IEEE)[\s/]+(?:ACM)[\s/]+(?:Transactions)[\s.]+(?:on[\s.]+)?(?:Computational Biology)",
        r"(?:Advanced Biology|Adv Biol)",
        r"(?:Biological Chemistry|Biol Chem|BiolChem)",
    ]
    for pattern in journal_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def _extract_metadata_llm(filepath: str, filename: str) -> dict | None:
    """Extract metadata using LLM from PDF header text.

    Uses BAML for title + author extraction, regex for year/journal.
    Returns None if no meaningful data could be extracted.
    """
    header_text = _extract_header_text(filepath)
    if not header_text or len(header_text) < 50:
        return None

    # Title via BAML (uses qwen3:32b via Ollama)
    llm_title = parse_title_with_baml(header_text)
    if not llm_title:
        return None

    title = _normalize_title(llm_title)
    if _title_quality_score(title) > 100:
        return None

    # Authors via BAML
    author_list = parse_authors_with_baml(header_text)

    # PDF-based author extraction as supplement
    pdf_authors_str = extract_authors_from_pdf(filepath)
    pdf_author_list = []
    if pdf_authors_str:
        pdf_author_list = [a.strip() for a in pdf_authors_str.split(",") if a.strip()]

    # Merge: BAML authors take priority, PDF authors as supplement
    all_authors = list(author_list) if author_list else []
    seen_lower = {a.lower() for a in all_authors}
    for a in pdf_author_list:
        if a.lower() not in seen_lower:
            all_authors.append(a)
            seen_lower.add(a.lower())

    authors = ", ".join(all_authors) if all_authors else "Unknown"

    # Year from header text
    year = _extract_year_from_text(header_text)

    # Journal from header text first, then filename
    journal = _extract_journal_from_header(header_text)
    if not journal:
        # Fallback: last comma-separated part of filename
        clean_name = filename.replace(".pdf", "").replace(".PDF", "").strip()
        parts = [p.strip() for p in clean_name.split(",")]
        if len(parts) >= 3:
            journal = parts[-1]

    return {
        "title": title,
        "authors": authors,
        "year": year or "Unknown",
        "journal": journal or "Unknown",
        "pmid": "",
        "doi": "",
    }


# ── Title quality helpers ───────────────────────────────────────────


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

    # ── 2. CrossRef via DOI (broader coverage than PubMed) ────────────
    if filepath and filepath.lower().endswith(".pdf"):
        crossref = extract_metadata_crossref(filepath)
        if crossref and crossref.get("title"):
            return {
                "title": crossref["title"],
                "authors": crossref["authors"] or "Unknown",
                "year": crossref["year"] or "Unknown",
                "journal": crossref["journal"] or "Unknown",
                "pmid": crossref.get("pmid", ""),
                "doi": crossref.get("doi", ""),
            }

    # ── 3. LLM-based extraction from PDF header (for no-DOI papers) ───
    if filepath and filepath.lower().endswith(".pdf") and use_hybrid_pipeline:
        llm_meta = _extract_metadata_llm(filepath, filename)
        if llm_meta and llm_meta.get("title") and llm_meta.get("authors") != "Unknown":
            return llm_meta

    # ── 4. Fallback: filename parsing ─────────────────────────────────
    clean_name = filename.replace(".pdf", "").replace(".PDF", "").strip()
    parts = [p.strip() for p in clean_name.split(",")]

    metadata = {
        "title": clean_name,
        "authors": "Unknown",
        "year": "Unknown",
        "journal": "Unknown",
        "pmid": "",
        "doi": "",
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
