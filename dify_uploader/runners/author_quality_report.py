import csv
from pathlib import Path
from typing import TypedDict

from dify_uploader.config import PDF_FOLDER
from dify_uploader.metadata import extract_metadata

ORG_KEYWORDS = {
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
    "molecular",
    "biology",
    "engineering",
    "site",
    "partner",
}


class ReportRow(TypedDict):
    file: str
    author_count: int
    author_issues: str
    author_warnings: str
    title: str
    title_issues: str
    extracted_authors: str


def _split_authors(authors_text: str | None) -> list[str]:
    if not authors_text:
        return []
    return [part.strip() for part in authors_text.split(",") if part.strip()]


def _contains_org_keywords(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ORG_KEYWORDS)


def _is_name_like(author: str) -> bool:
    tokens = [t.strip(". ") for t in author.split() if t.strip(". ")]
    if len(tokens) < 2:
        return False
    if len(tokens) > 7:
        return False
    if any(any(ch.isdigit() for ch in token) for token in tokens):
        return False
    return True


def _detect_issues(authors: list[str], raw_text: str) -> list[str]:
    issues, _ = _detect_author_findings(authors, raw_text, "")
    return issues


def _detect_author_findings(
    authors: list[str], raw_text: str, title: str
) -> tuple[list[str], list[str]]:
    issues = []
    warnings: list[str] = []
    if not authors:
        issues.append("no_authors")
        return issues, warnings

    has_org_keywords = _contains_org_keywords(raw_text)
    if has_org_keywords:
        issues.append("contains_org_keyword")

    non_name_like = [a for a in authors if not _is_name_like(a)]
    if non_name_like:
        issues.append("non_name_like_entry")

    if len(authors) == 1:
        issues.append("single_author_only")

    lowered_title = (title or "").lower()
    is_consoritum_like_title = any(
        marker in lowered_title
        for marker in {
            "perspective",
            "review",
            "consortia",
            "consortium",
            "opinion",
        }
    )
    max_authors_before_flag = 40 if is_consoritum_like_title else 20

    if len(authors) > max_authors_before_flag:
        # Long but otherwise plausible author lists are treated as policy warnings,
        # not extraction-quality errors.
        if not has_org_keywords and not non_name_like:
            warnings.append("many_plausible_authors")
        else:
            issues.append("unusually_many_authors")

    return issues, warnings


def _detect_title_issues(title: str, filename: str) -> list[str]:
    issues = []
    value = (title or "").strip()
    lowered = value.lower()

    if not value:
        issues.append("no_title")
        return issues
    if len(value) < 12:
        issues.append("short_title")
    if ".pdf" in lowered:
        issues.append("contains_file_extension")
    if value.count(",") >= 2 and any(ch.isdigit() for ch in value):
        issues.append("looks_like_filename_title")

    noisy_markers = {
        "open access",
        "research article",
        "abstract",
        "creative commons",
        "doi",
        "received",
        "accepted",
    }
    if any(marker in lowered for marker in noisy_markers):
        issues.append("contains_header_noise")

    if (
        value.strip().lower()
        == filename.replace(".pdf", "").replace(".PDF", "").strip().lower()
    ):
        issues.append("same_as_filename")

    return issues


def run_author_quality_report(
    folder: str | None = None,
    output_csv: str | None = None,
    max_files: int | None = None,
) -> int:
    base_folder = Path(folder or PDF_FOLDER)
    if not base_folder.exists() or not base_folder.is_dir():
        print(f"Folder not found: {base_folder}")
        return 1

    pdf_files = sorted(base_folder.glob("*.pdf"))
    if max_files is not None and max_files > 0:
        pdf_files = pdf_files[:max_files]

    if not pdf_files:
        print(f"No PDF files found in: {base_folder}")
        return 1

    report_path = Path(output_csv or "reports/author_quality_report.csv")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[ReportRow] = []
    for pdf_file in pdf_files:
        metadata = extract_metadata(pdf_file.name, str(pdf_file))
        extracted = str(metadata.get("authors") or "")
        authors = _split_authors(extracted)
        author_issues, author_warnings = _detect_author_findings(
            authors, extracted or "", str(metadata.get("title") or "")
        )
        title = str(metadata.get("title") or "")
        title_issues = _detect_title_issues(title, pdf_file.name)
        rows.append(
            {
                "file": pdf_file.name,
                "author_count": len(authors),
                "author_issues": ";".join(author_issues),
                "author_warnings": ";".join(author_warnings),
                "title": title,
                "title_issues": ";".join(title_issues),
                "extracted_authors": extracted or "",
            }
        )

    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "file",
                "author_count",
                "author_issues",
                "author_warnings",
                "title",
                "title_issues",
                "extracted_authors",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    checked = len(rows)
    with_authors = len([row for row in rows if row["author_count"] > 0])
    author_issue_rows = [row for row in rows if row["author_issues"]]
    author_warning_rows = [row for row in rows if row["author_warnings"]]
    title_issue_rows = [row for row in rows if row["title_issues"]]

    print(f"Checked files: {checked}")
    print(f"With extracted authors: {with_authors}")
    print(f"Rows with author issues: {len(author_issue_rows)}")
    print(f"Rows with author warnings: {len(author_warning_rows)}")
    print(f"Rows with title issues: {len(title_issue_rows)}")
    print(f"CSV report: {report_path}")

    for row in author_issue_rows[:10]:
        print(
            f"- AUTHOR {row['file']}: {row['author_issues']} | {row['extracted_authors']}"
        )

    for row in title_issue_rows[:10]:
        print(f"- TITLE {row['file']}: {row['title_issues']} | {row['title']}")

    for row in author_warning_rows[:10]:
        print(
            f"- AUTHOR-WARN {row['file']}: {row['author_warnings']} | {row['extracted_authors']}"
        )

    return 0


def main() -> int:
    return run_author_quality_report()
