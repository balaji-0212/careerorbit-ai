"""Shared request headers for the synthetic account in the hermetic API suite."""


def authenticated_headers(method: str, headers: dict | None = None) -> dict:
    result = dict(headers or {})
    unauthenticated = any(key.lower() == "x-test-unauthenticated" for key in result)
    result = {key: value for key, value in result.items() if key.lower() != "x-test-unauthenticated"}
    if unauthenticated:
        return result

    lowered = {key.lower() for key in result}
    if "cookie" not in lowered:
        result["Cookie"] = "careerorbit_session=test-session-token; careerorbit_csrf=test-csrf-token"
    if method.upper() not in {"GET", "HEAD", "OPTIONS"} and "x-csrf-token" not in lowered:
        result["X-CSRF-Token"] = "test-csrf-token"
    return result
