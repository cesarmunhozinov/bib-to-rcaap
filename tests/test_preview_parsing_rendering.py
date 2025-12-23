import app


def test_build_display_entry_defaults_and_mapping():
    raw = [
        {
            "title": "Sample Title",
            "author": "Alice Example and Bob Tester",
            "booktitle": "Conf X",
            "year": "2024",
            "abstract": "Something",
        },
        {"title": None},
    ]

    display_list = [app._build_display_entry(e) for e in raw]

    assert len(display_list) == 2
    first = display_list[0]
    assert first["display_title"] == "Sample Title"
    assert first["display_authors"] == "Example, A.; Tester, B."
    assert first["display_venue"] == "Conf X"
    assert first["display_year"] == "2024"
    assert first["display_abstract"] == "Something"

    second = display_list[1]
    assert second["display_title"] == "Untitled"
    assert second["display_authors"] == "Unknown Author"
    assert second["display_venue"] == "N/A"
    assert second["display_year"] == ""
    assert second["display_abstract"] == "No abstract in BibTeX"


def test_display_preview_safe_renders_expected(monkeypatch):
    calls = []

    class FakeSt:
        def markdown(self, text, unsafe_allow_html=False):
            calls.append(text)

        def write(self, text):
            calls.append(text)

        def error(self, text):
            calls.append(text)

    fake = FakeSt()
    monkeypatch.setattr(app, "st", fake)

    entries = [
        {
            "display_title": "Preview Paper",
            "display_authors": "One, A.; Two, B.",
            "display_venue": "Venue Y",
            "display_year": "2025",
        }
    ]

    app.display_preview_safe(entries)

    assert any("Preview Paper" in c for c in calls)
    assert any("One, A.; Two, B." in c for c in calls)
    assert any("Venue Y, 2025" in c for c in calls)
