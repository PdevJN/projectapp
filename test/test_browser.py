import pytest

from projectapp.browser import open_url


def test_open_url_passes_the_url_to_the_opener() -> None:
    opened: list[str] = []
    open_url("https://example.com/1", opener=lambda url: opened.append(url) or True)
    assert opened == ["https://example.com/1"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "example.com", ""])
def test_open_url_refuses_urls_that_are_not_http(url: str) -> None:
    opened: list[str] = []
    with pytest.raises(OSError):
        open_url(url, opener=lambda u: opened.append(u) or True)
    assert opened == []


def test_open_url_raises_when_the_browser_cannot_be_opened() -> None:
    with pytest.raises(OSError, match="ブラウザ"):
        open_url("https://example.com", opener=lambda url: False)
