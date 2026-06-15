import os
import sys
from typing import Any

_WARNED_IMPORT = False
_WARNED_CALL = False


def _trace_enabled() -> bool:
    return os.getenv("AUTHOR_EXTRACTION_TRACE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _trace(message: str) -> None:
    if _trace_enabled():
        print(f"[author-baml-trace] {message}", file=sys.stderr)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def parse_authors_with_baml(header_text: str) -> list[str]:
    global _WARNED_IMPORT, _WARNED_CALL
    if not str(header_text or "").strip():
        return []

    # Allow disabling in environments where no Ollama/BAML runtime is available.
    enabled = os.getenv("AUTHOR_EXTRACTION_ENABLE_LLM_FALLBACK", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return []

    # Do not pin a host here; use externally configured runtime defaults.
    os.environ.setdefault("BAML_OLLAMA_MODEL", "qwen3:32b")

    _trace(
        "authors-call: enabled=true, "
        f"base_url={os.getenv('BAML_OLLAMA_BASE_URL', '<unset>')}, "
        f"model={os.getenv('BAML_OLLAMA_MODEL', '<unset>')}, "
        f"chars={len(str(header_text or ''))}"
    )

    try:
        from dify_uploader.baml_client.sync_client import b  # type: ignore
    except Exception as exc:
        if not _WARNED_IMPORT:
            print(
                f"[author-baml] import failed, fallback disabled for this run: {exc}",
                file=sys.stderr,
            )
            _WARNED_IMPORT = True
        return []

    try:
        result = b.ExtractAuthorsFromHeader(header_text)
    except Exception as exc:
        if not _WARNED_CALL:
            print(
                f"[author-baml] call failed, fallback disabled for this run: {exc}",
                file=sys.stderr,
            )
            _WARNED_CALL = True
        return []

    _trace("authors-call: success")

    # BAML pydantic object or dict-like fallback.
    if hasattr(result, "authors"):
        return _as_list(getattr(result, "authors"))
    if isinstance(result, dict):
        return _as_list(result.get("authors"))
    return []


def parse_title_with_baml(header_text: str) -> str | None:
    global _WARNED_IMPORT, _WARNED_CALL

    if not str(header_text or "").strip():
        return None

    enabled = os.getenv("TITLE_EXTRACTION_ENABLE_LLM_FALLBACK", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None

    # Do not pin a host here; use externally configured runtime defaults.
    os.environ.setdefault("BAML_OLLAMA_MODEL", "qwen3:32b")

    _trace(
        "title-call: enabled=true, "
        f"base_url={os.getenv('BAML_OLLAMA_BASE_URL', '<unset>')}, "
        f"model={os.getenv('BAML_OLLAMA_MODEL', '<unset>')}, "
        f"chars={len(str(header_text or ''))}"
    )

    try:
        from dify_uploader.baml_client.sync_client import b  # type: ignore
    except Exception as exc:
        if not _WARNED_IMPORT:
            print(
                f"[title-baml] import failed, fallback disabled for this run: {exc}",
                file=sys.stderr,
            )
            _WARNED_IMPORT = True
        return None

    try:
        result = b.ExtractTitleFromHeader(header_text)
    except Exception as exc:
        if not _WARNED_CALL:
            print(
                f"[title-baml] call failed, fallback disabled for this run: {exc}",
                file=sys.stderr,
            )
            _WARNED_CALL = True
        return None

    _trace("title-call: success")

    if hasattr(result, "title"):
        text = str(getattr(result, "title") or "").strip()
        return text or None
    if isinstance(result, dict):
        text = str(result.get("title") or "").strip()
        return text or None
    return None
