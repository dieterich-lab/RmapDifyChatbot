import json
import os
import time

import requests

from dify_uploader.config import DATASET_ID, DIFY_API_URL, get_headers


def upload_variant(
    filepath: str, filename: str, variant_name: str, indexing_data: dict
):
    url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/document/create-by-file"
    ext = os.path.splitext(filename)[1].lower()
    mime_type = "application/pdf" if ext == ".pdf" else "text/plain"

    with open(filepath, "rb") as f:
        file_size = os.path.getsize(filepath)
        files = {
            "file": (filename, f, mime_type),
            "data": (None, json.dumps(indexing_data), "text/plain"),
        }

        print(f"Uploading ({variant_name}): {filename}...")
        print(f"File size: {file_size} bytes")
        print(f"Endpoint: {url}")
        print(f"Payload(data): {json.dumps(indexing_data, ensure_ascii=False)}")

        response = requests.post(url, headers=get_headers(), files=files, timeout=120)

        if response.status_code == 200:
            response_json = response.json()
            doc = response_json.get("document", {})
            doc_id = doc.get("id")
            print(f"✅ Success! Doc ID: {doc_id}")
            print(f"   API response document name: {doc.get('name')}")
            print(f"   API response parsing status: {doc.get('parsing_status')}")
            print(
                f"   API response tokens/words: {doc.get('tokens')}/{doc.get('word_count')}"
            )
            print(f"   API raw response: {json.dumps(response_json, ensure_ascii=False)}")
            if doc_id:
                result = wait_for_indexing(doc_id)
                result["variant"] = variant_name
                result["document_id"] = doc_id
                return result
            return {
                "variant": variant_name,
                "document_id": None,
                "error": "no document id",
            }

        print(f"❌ API error {response.status_code}: {response.text}")
        return {
            "variant": variant_name,
            "document_id": None,
            "error": f"api_error_{response.status_code}",
            "raw": response.text,
        }


def wait_for_indexing(
    document_id: str, timeout_seconds: int = 180, poll_seconds: int = 5
):
    status_url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/documents/{document_id}"

    print("Waiting for indexing...")
    start = time.time()

    while time.time() - start < timeout_seconds:
        response = requests.get(
            status_url,
            headers=get_headers(),
            params={"metadata": "all"},
            timeout=60,
        )
        if response.status_code != 200:
            print(f"❌ Status API error {response.status_code}: {response.text}")
            return {
                "indexing_status": "status_api_error",
                "display_status": None,
                "word_count": None,
                "segment_count": None,
                "metadata_count": None,
                "error": response.text,
            }

        doc = response.json()
        status = doc.get("indexing_status")
        display_status = doc.get("display_status")
        word_count = doc.get("word_count")
        error = doc.get("error")
        doc_metadata = doc.get("doc_metadata", [])

        print(
            f"   Status={status}, Display={display_status}, Words={word_count}, "
            f"Metadata fields={len(doc_metadata)}, Error={error}"
        )

        if status in {"completed", "error", "failed"}:
            print(f"   Final document response: {json.dumps(doc, ensure_ascii=False)}")
            return {
                "indexing_status": status,
                "display_status": display_status,
                "word_count": word_count,
                "segment_count": doc.get("segment_count"),
                "metadata_count": len(doc_metadata),
                "error": error,
            }

        time.sleep(poll_seconds)

    print("⏰ Timeout while waiting for indexing. Please try again later.")
    return {
        "indexing_status": "timeout",
        "display_status": None,
        "word_count": None,
        "segment_count": None,
        "metadata_count": None,
        "error": "timeout",
    }


def get_document_detail(document_id: str) -> dict | None:
    status_url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/documents/{document_id}"
    response = requests.get(
        status_url, headers=get_headers(), params={"metadata": "all"}, timeout=60
    )
    if response.status_code != 200:
        print(f"❌ Document detail API error {response.status_code}: {response.text}")
        return None
    return response.json()


def get_dataset_metadata_fields() -> list[dict]:
    url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/metadata"
    response = requests.get(url, headers=get_headers(), timeout=60)
    if response.status_code != 200:
        print(f"❌ Dataset metadata API error {response.status_code}: {response.text}")
        return []

    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("doc_metadata"), list):
        return data["doc_metadata"]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return []


def ensure_metadata_fields_exist(metadata: dict) -> dict:
    fields = get_dataset_metadata_fields()
    name_to_id = {
        str(item.get("name")): str(item.get("id"))
        for item in fields
        if item.get("name") and item.get("id")
    }

    for key in metadata.keys():
        if key in name_to_id:
            continue

        create_url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/metadata"
        create_payload = {"name": str(key), "type": "string"}
        print(f"Creating metadata field: {create_payload}")
        create_response = requests.post(
            create_url, headers=get_headers(), json=create_payload, timeout=60
        )
        if create_response.status_code not in (200, 201):
            print(
                f"❌ Metadata field could not be created ({create_response.status_code}): "
                f"{create_response.text}"
            )
            continue

    fields = get_dataset_metadata_fields()
    return {
        str(item.get("name")): str(item.get("id"))
        for item in fields
        if item.get("name") and item.get("id")
    }


def apply_metadata_two_pass(document_id: str, metadata: dict) -> dict:
    url = f"{DIFY_API_URL}/datasets/{DATASET_ID}/documents/metadata"
    name_to_id = ensure_metadata_fields_exist(metadata)

    missing_keys = [k for k in metadata.keys() if k not in name_to_id]
    if missing_keys:
        return {
            "ok": False,
            "attempt": None,
            "status_code": None,
            "response": f"missing metadata field ids for: {missing_keys}",
        }

    payload = {
        "operation_data": [
            {
                "document_id": document_id,
                "partial_update": True,
                "metadata_list": [
                    {"id": name_to_id[str(k)], "name": str(k), "value": str(v)}
                    for k, v in metadata.items()
                ],
            }
        ]
    }

    print("Attempting metadata patch with field UUIDs...")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    response = requests.post(url, headers=get_headers(), json=payload, timeout=60)
    if response.status_code == 200:
        print("✅ Metadata update successful.")
        return {
            "ok": True,
            "attempt": 1,
            "status_code": response.status_code,
            "response": response.text,
        }

    print(
        f"❌ Metadata-Update fehlgeschlagen ({response.status_code}): {response.text}"
    )
    return {
        "ok": False,
        "attempt": None,
        "status_code": response.status_code,
        "response": response.text,
    }
