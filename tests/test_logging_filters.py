import logging

from src.outlook_categorizer.cli import _HttpxRequestInfoToDebugFilter


def test_httpx_request_info_is_downgraded_to_debug() -> None:
    """Ensure httpx request logs are suppressed unless running at DEBUG."""

    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST https://example.com \"HTTP/1.1 200 OK\"",
        args=(),
        exc_info=None,
    )

    root_logger = logging.getLogger()
    previous_level = root_logger.level

    try:
        root_logger.setLevel(logging.INFO)
        f = _HttpxRequestInfoToDebugFilter()
        assert f.filter(record) is False

        root_logger.setLevel(logging.DEBUG)
        assert f.filter(record) is True
    finally:
        root_logger.setLevel(previous_level)
