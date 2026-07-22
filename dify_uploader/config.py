import os

DIFY_API_URL = os.getenv("DIFY_API_URL", "http://rmap-chatbot-demo-dify/v1")
# Preferred explicit name for dataset operations (paper upload/metadata update).
# Backward-compatible fallback: DIFY_API_KEY.
DIFY_DATASET_API_KEY = os.getenv(
    "DIFY_DATASET_API_KEY",
    os.getenv("DIFY_API_KEY"),
)

# Backward-compatible alias kept for existing imports.
DIFY_API_KEY = DIFY_DATASET_API_KEY
DATASET_ID = os.getenv("DIFY_DATASET_ID", "<your-dataset-id>")
PDF_FOLDER = os.getenv("PDF_FOLDER", "./RMaP papers first funding period")


def get_headers() -> dict[str, str]:
    if not DIFY_DATASET_API_KEY:
        raise ValueError(
            "Missing DIFY_DATASET_API_KEY (or legacy DIFY_API_KEY) for dataset upload endpoints."
        )

    if not DIFY_DATASET_API_KEY.startswith("dataset-"):
        raise ValueError(
            "DIFY_DATASET_API_KEY must be a dataset key (prefix 'dataset-'). "
            "App keys (prefix 'app-') are only valid for /v1 app endpoints such as chat-messages."
        )

    return {"Authorization": f"Bearer {DIFY_DATASET_API_KEY}"}


def get_first_pdf_file() -> tuple[str, str] | None:
    for filename in os.listdir(PDF_FOLDER)[:1]:
        if filename.lower().endswith(".pdf"):
            return filename, os.path.join(PDF_FOLDER, filename)
    return None


def get_pdf_files(folder: str | None = None) -> list[tuple[str, str]]:
    target_folder = folder or PDF_FOLDER
    pdf_files: list[tuple[str, str]] = []
    for filename in sorted(os.listdir(target_folder)):
        if filename.lower().endswith(".pdf"):
            pdf_files.append((filename, os.path.join(target_folder, filename)))
    return pdf_files
