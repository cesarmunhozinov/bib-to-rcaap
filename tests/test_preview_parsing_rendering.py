import app


def test_defensive_parse_entries_defaults():
    raw = [
        {
            "title": "Sample Title",
            "author": "Alice Example and Bob Tester",
            "booktitle": "Conf X",
            "year": "2024",
            "doi": "10.1000/xyz",
            "url": "http://example.com",
        },
        {"title": None},
    ]

    parsed = app._defensive_parse_entries(raw)

    assert len(parsed) == 2
    first = parsed[0]
    assert first["Title"] == "Sample Title"
    assert first["Authors"] == ["Alice Example", "Bob Tester"]
    assert first["Venue"] == "Conf X"
    assert first["Year"] == "2024"
    assert first["DOI"] == "10.1000/xyz"
    assert first["URL"] == "http://example.com"

    second = parsed[1]
    assert second["Title"] == "Unknown Title"
    assert second["Authors"] == []
    assert second["Venue"] == "Unknown Venue"
    assert second["Year"] == "Unknown Year"


def test_render_scholar_ui_semicolon_and_layout(monkeypatch):
    calls = []

    class FakeSt:
        def markdown(self, text, unsafe_allow_html=False):
            calls.append(text)

        def write(self, text):
            calls.append(text)

    fake = FakeSt()
    monkeypatch.setattr(app, "st", fake)

    entry = {
        "Title": "Preview Paper",
        "Authors": ["Author One", "Author Two"],
        "Venue": "Venue Y",
        "Year": "2025",
        "DOI": None,
    }

    app.render_scholar_ui(entry)

    # Title rendered in bold
    assert any("**" in c for c in calls)
    # Authors joined with semicolons
    assert any("Author One; Author Two" in c for c in calls)
    # Venue and Year line present
    assert any("Venue Y (2025)" in c for c in calls)
