import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_graphql(url: str, query: str, timeout: int = 10):
    payload = json.dumps({"query": query}).encode("utf-8")
    request = Request(
        url=url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return True, response.getcode(), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, exc.code, body
    except URLError as exc:
        return False, None, f"URLError: {exc}"
    except Exception as exc:
        return False, None, f"Exception: {exc}"


def test_endpoint(url: str, timeout: int = 10) -> dict:
    # We first ask for available classes, then try a minimal GraphQL aggregate.
    schema_url = url.replace("/v1/graphql", "/v1/schema")

    try:
        req = Request(schema_url, method="GET")
        with urlopen(req, timeout=timeout) as response:
            schema_body = response.read().decode("utf-8", errors="replace")
            schema = json.loads(schema_body)
    except Exception as exc:
        return {
            "url": url,
            "reachable": False,
            "stage": "schema",
            "error": str(exc),
        }

    classes = [c.get("class") for c in schema.get("classes", []) if c.get("class")]

    aggregate_query = "{ Aggregate { Document { meta { count } } } }"
    ok, status, body = post_graphql(url, aggregate_query, timeout=timeout)

    result = {
        "url": url,
        "reachable": ok,
        "status": status,
        "known_classes": classes,
    }

    if ok:
        try:
            result["graphql"] = json.loads(body)
        except ValueError:
            result["graphql_raw"] = body
    else:
        result["error"] = body

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test Weaviate reachability and GraphQL."
    )
    parser.add_argument(
        "--url",
        default="http://weaviate:8080/v1/graphql",
        help="Weaviate GraphQL endpoint",
    )
    parser.add_argument(
        "--also-localhost",
        action="store_true",
        help="Additionally test http://localhost:8080/v1/graphql",
    )
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    targets = [args.url]
    if args.also_localhost and "localhost" not in args.url:
        targets.append("http://localhost:8080/v1/graphql")

    reports = [test_endpoint(target, timeout=args.timeout) for target in targets]
    print(json.dumps(reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
