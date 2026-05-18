from dify_uploader.runners import DEFAULT_TARGET_AUTHORS
from dify_uploader.workflows import run_selected_authors_two_pass


def main() -> int:
    run_selected_authors_two_pass(DEFAULT_TARGET_AUTHORS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
