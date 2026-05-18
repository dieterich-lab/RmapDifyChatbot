import os

DIFY_API_URL = "http://rmap-chatbot-demo-dify/v1"
DIFY_API_KEY = "dataset-z3bHkQ6eUPKN21GaLq3KXIiS"
DATASET_ID = "227cf97a-8e56-4cd6-808d-caf57bc0d2bf"
PDF_FOLDER = "./RMaP papers first funding period"


def get_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {DIFY_API_KEY}"}


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
