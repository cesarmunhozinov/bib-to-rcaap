import pytest

from app import extract_doi


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("10.3390/joitmc7010070", "10.3390/joitmc7010070"),
        ("https://doi.org/10.3390/joitmc7010070", "10.3390/joitmc7010070"),
        ("https://doi.org/10.3390/joitmc7010070.", "10.3390/joitmc7010070"),
        ("https://example.com/article?doi=10.1000/abc123", "10.1000/abc123"),
        ("https://publisher.com/article/10.1038/s41586-020-2649-2", "10.1038/s41586-020-2649-2"),
        ("https://sciencedirect.com/article/pii/S0920548917313617", None),
        ("Some random text without a DOI", None),
        ("(10.1000/xyz),", "10.1000/xyz"),
    ],
)
def test_extract_doi(input_, expected):
    assert extract_doi(input_) == expected
