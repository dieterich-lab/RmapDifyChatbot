def main(result=None):

    # Make sure we have a list
    items = result if isinstance(result, list) else []

    # Dify Array[object] limit
    items = items[:30]

    doc_names = []

    for item in items:
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") or {}

        doc_name = (
            metadata.get("document_name")
            or metadata.get("doc_name")
            or item.get("title")
        )

        if doc_name and doc_name not in doc_names:
            doc_names.append(doc_name)

    return {
        "result": items,
        "doc_names": doc_names
    }