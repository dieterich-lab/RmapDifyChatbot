import os
import time

from dify_uploader.client import (
    apply_metadata_two_pass,
    get_document_detail,
    upload_variant,
)
from dify_uploader.config import PDF_FOLDER, get_first_pdf_file, get_pdf_files
from dify_uploader.metadata import extract_metadata


def run_two_pass_test(filepath: str, filename: str, metadata: dict):
    run_tag = str(int(time.time()))
    pdf_ext = os.path.splitext(filename)[1]
    pdf_base = os.path.splitext(filename)[0]
    unique_pdf_filename = f"{pdf_base}__two_pass_{run_tag}{pdf_ext}"

    upload_payload = {
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"},
        "duplicate": False,
    }

    upload_result = upload_variant(
        filepath, unique_pdf_filename, "two_pass_upload", upload_payload
    )
    document_id = upload_result.get("document_id")
    if not document_id:
        print("❌ No document_id returned by upload, aborting two-pass test.")
        return

    metadata_result = apply_metadata_two_pass(document_id, metadata)
    detail = get_document_detail(document_id)

    built_in_names = {
        "document_name",
        "uploader",
        "upload_date",
        "last_update_date",
        "source",
    }
    custom_names = []
    if detail and isinstance(detail.get("doc_metadata"), list):
        custom_names = [
            item.get("name")
            for item in detail.get("doc_metadata", [])
            if item.get("name") not in built_in_names
        ]

    print("\n===== TWO-PASS RESULT SUMMARY =====")
    print(
        f"Upload: status={upload_result.get('indexing_status')}, "
        f"segments={upload_result.get('segment_count')}, doc_id={document_id}"
    )
    print(
        f"Metadata pass: ok={metadata_result.get('ok')}, "
        f"attempt={metadata_result.get('attempt')}"
    )
    if detail:
        print(
            f"Document now: metadata_fields={len(detail.get('doc_metadata', []))}, "
            f"custom_metadata_names={custom_names}, doc_type={detail.get('doc_type')}"
        )


def run_abc_test(filepath: str, filename: str, metadata: dict):
    run_tag = str(int(time.time()))
    pdf_ext = os.path.splitext(filename)[1]
    pdf_base = os.path.splitext(filename)[0]
    unique_pdf_filename = f"{pdf_base}__api_abcd_{run_tag}{pdf_ext}"

    payload_a = {
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"},
        "duplicate": False,
    }

    payload_b = {
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"},
        "doc_type": "others",
        "doc_metadata": metadata,
        "duplicate": False,
    }

    result_a = upload_variant(
        filepath, unique_pdf_filename, "A_minimal_unique", payload_a
    )
    result_b = upload_variant(
        filepath, unique_pdf_filename, "B_with_metadata_unique", payload_b
    )

    txt_filename = f"api_ab_test_sample_{run_tag}.txt"
    txt_filepath = os.path.join(PDF_FOLDER, txt_filename)
    txt_content = (
        "This is a plain text API upload test for Dify indexing.\n"
        "If this file is parsed into segments while PDF is not, the issue is PDF-path specific.\n"
        "RMaP test marker: 2026-05-06.\n"
    )
    with open(txt_filepath, "w", encoding="utf-8") as tf:
        tf.write(txt_content)

    payload_c = {
        "indexing_technique": "high_quality",
        "process_rule": {"mode": "automatic"},
        "duplicate": False,
    }
    result_c = upload_variant(
        txt_filepath, txt_filename, "C_txt_minimal_unique", payload_c
    )

    print("\n===== A/B/C RESULT SUMMARY =====")
    for result in [result_a, result_b, result_c]:
        print(
            f"{result.get('variant')}: status={result.get('indexing_status')}, "
            f"display={result.get('display_status')}, words={result.get('word_count')}, "
            f"segments={result.get('segment_count')}, metadata_fields={result.get('metadata_count')}, "
            f"error={result.get('error')}, doc_id={result.get('document_id')}"
        )


def run_default() -> None:
    first_pdf = get_first_pdf_file()
    if not first_pdf:
        print("❌ No PDF file found in the folder.")
        return

    filename, filepath = first_pdf
    metadata = extract_metadata(filename, filepath, use_hybrid_pipeline=True)
    run_two_pass_test(filepath, filename, metadata)


def run_selected_authors_two_pass(
    target_authors: list[str], folder: str | None = None
) -> None:
    pdf_files = get_pdf_files(folder)
    if not pdf_files:
        print("❌ No PDF file found in the folder.")
        return

    target_names = [name.strip() for name in target_authors if name.strip()]
    if not target_names:
        print("❌ No target authors provided.")
        return

    target_names_lower = [name.lower() for name in target_names]
    considered = 0
    matched = 0

    print("\n===== SELECTED AUTHORS RUN =====")
    print(f"Folder: {folder or PDF_FOLDER}")
    print(f"Target authors: {', '.join(target_names)}")

    for filename, filepath in pdf_files:
        considered += 1
        metadata = extract_metadata(filename, filepath, use_hybrid_pipeline=True)
        authors_text = str(metadata.get("authors", ""))
        authors_text_lower = authors_text.lower()

        has_match = any(name in authors_text_lower for name in target_names_lower)
        if not has_match:
            print(f"SKIP {filename}: no target-author match")
            continue

        matched += 1
        print(f"MATCH {filename}: {authors_text}")
        run_two_pass_test(filepath, filename, metadata)

    print("\n===== SELECTED AUTHORS SUMMARY =====")
    print(f"PDF files scanned: {considered}")
    print(f"PDF files matched: {matched}")


def run_all_two_pass(folder: str | None = None) -> None:
    pdf_files = get_pdf_files(folder)
    if not pdf_files:
        print("❌ No PDF file found in the folder.")
        return

    print("\n===== BULK TWO-PASS RUN =====")
    print(f"Folder: {folder or PDF_FOLDER}")
    print("Metadata pipeline: hybrid title+author extraction")

    uploaded = 0
    failed = 0

    for filename, filepath in pdf_files:
        try:
            metadata = extract_metadata(filename, filepath, use_hybrid_pipeline=True)
            print(
                f"\nUPLOAD {filename}: title='{metadata.get('title')}', "
                f"authors='{metadata.get('authors')}'"
            )
            run_two_pass_test(filepath, filename, metadata)
            uploaded += 1
        except Exception as exc:
            failed += 1
            print(f"❌ Error while processing {filename}: {exc}")

    print("\n===== BULK TWO-PASS SUMMARY =====")
    print(f"PDF files processed: {len(pdf_files)}")
    print(f"Uploads attempted: {uploaded}")
    print(f"Failures: {failed}")
