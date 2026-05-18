import argparse
import os

from dify_uploader.config import PDF_FOLDER, get_first_pdf_file
from dify_uploader.metadata import extract_metadata
from dify_uploader.runners.author_quality_report import run_author_quality_report
from dify_uploader.workflows import (
    run_all_two_pass,
    run_abc_test,
    run_default,
    run_selected_authors_two_pass,
    run_two_pass_test,
)

DEFAULT_SELECTED_AUTHORS = ["Mark Helm", "Christoph Dieterich"]


def _resolve_input_file(file_path: str | None) -> tuple[str, str] | None:
    if file_path:
        filename = os.path.basename(file_path)
        return filename, file_path
    return get_first_pdf_file()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dify-upload",
        description="Upload and test Dify document ingestion workflows.",
    )

    subparsers = parser.add_subparsers(dest="command")

    default_parser = subparsers.add_parser(
        "default",
        help="Run the default two-pass workflow on the first PDF in the configured folder.",
    )
    default_parser.set_defaults(command="default")

    two_pass_parser = subparsers.add_parser(
        "two-pass",
        help="Run two-pass upload + metadata update for a specific file or first PDF.",
    )
    two_pass_parser.add_argument(
        "--file",
        dest="file_path",
        help="Path to a PDF file. If omitted, first PDF in configured folder is used.",
    )
    two_pass_parser.set_defaults(command="two-pass")

    abc_parser = subparsers.add_parser(
        "abc-test",
        help="Run A/B/C API diagnostics for a specific file or first PDF.",
    )
    abc_parser.add_argument(
        "--file",
        dest="file_path",
        help="Path to a PDF file. If omitted, first PDF in configured folder is used.",
    )
    abc_parser.set_defaults(command="abc-test")

    meta_parser = subparsers.add_parser(
        "metadata",
        help="Print extracted metadata for a specific file or first PDF.",
    )
    meta_parser.add_argument(
        "--file",
        dest="file_path",
        help="Path to a PDF file. If omitted, first PDF in configured folder is used.",
    )
    meta_parser.set_defaults(command="metadata")

    selected_parser = subparsers.add_parser(
        "selected-authors",
        help="Run two-pass upload only for PDFs matching selected author names.",
    )
    selected_parser.add_argument(
        "--author",
        dest="authors",
        action="append",
        help=(
            "Author name to match. Can be passed multiple times. "
            "Default: Mark Helm and Christoph Dieterich."
        ),
    )
    selected_parser.add_argument(
        "--folder",
        dest="folder",
        help="Folder to scan for PDFs. Defaults to configured PDF folder.",
    )
    selected_parser.set_defaults(command="selected-authors")

    quality_parser = subparsers.add_parser(
        "author-quality",
        help="Create CSV quality report for extracted authors across PDFs.",
    )
    quality_parser.add_argument(
        "--folder",
        dest="folder",
        help="Folder to scan for PDFs. Defaults to configured PDF folder.",
    )
    quality_parser.add_argument(
        "--output",
        dest="output_csv",
        help="CSV output path. Default: reports/author_quality_report.csv",
    )
    quality_parser.add_argument(
        "--max-files",
        dest="max_files",
        type=int,
        help="Optional limit for number of PDFs to process.",
    )
    quality_parser.set_defaults(command="author-quality")

    bulk_parser = subparsers.add_parser(
        "bulk-two-pass",
        help="Run two-pass upload for all PDFs in a folder using hybrid metadata extraction.",
    )
    bulk_parser.add_argument(
        "--folder",
        dest="folder",
        help="Folder to scan for PDFs. Defaults to configured PDF folder.",
    )
    bulk_parser.set_defaults(command="bulk-two-pass")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command or args.command == "default":
        run_default()
        return 0

    if args.command == "selected-authors":
        target_authors = args.authors or DEFAULT_SELECTED_AUTHORS
        run_selected_authors_two_pass(target_authors, folder=args.folder)
        return 0

    if args.command == "author-quality":
        return run_author_quality_report(
            folder=args.folder,
            output_csv=args.output_csv,
            max_files=args.max_files,
        )

    if args.command == "bulk-two-pass":
        run_all_two_pass(folder=args.folder)
        return 0

    selected = _resolve_input_file(getattr(args, "file_path", None))
    if not selected:
        print(f"No PDF file found in configured folder: {PDF_FOLDER}")
        return 1

    filename, filepath = selected
    metadata = extract_metadata(filename, filepath, use_hybrid_pipeline=True)

    if args.command == "two-pass":
        run_two_pass_test(filepath, filename, metadata)
        return 0

    if args.command == "abc-test":
        run_abc_test(filepath, filename, metadata)
        return 0

    if args.command == "metadata":
        for key, value in metadata.items():
            print(f"{key}: {value}")
        return 0

    parser.print_help()
    return 1
