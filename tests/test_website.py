"""Checks for the static editorial draft (not the local Flask application)."""

from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlsplit


SITE = Path(__file__).resolve().parents[1] / "website"
PAGES = {"index.html": "pt-BR", "en.html": "en", "fr.html": "fr", "es.html": "es"}
ABOUT_IDS = {"index.html": "sobre", "en.html": "about", "fr.html": "apropos", "es.html": "acerca"}
CONTACT_IDS = {"index.html": "contato", "en.html": "contact", "fr.html": "contact", "es.html": "contacto"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.language = None
        self.current_languages = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.language = attrs.get("lang")
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])
        if tag == "a" and attrs.get("aria-current") == "page":
            self.current_languages += 1


class WebsiteTests(unittest.TestCase):
    def test_four_languages_and_local_links(self):
        for filename, language in PAGES.items():
            with self.subTest(filename=filename):
                raw = (SITE / filename).read_text(encoding="utf-8")
                page = Page()
                page.feed(raw)
                self.assertEqual(page.language, language)
                self.assertEqual(page.current_languages, 1)
                self.assertIn(ABOUT_IDS[filename], page.ids)
                self.assertIn(CONTACT_IDS[filename], page.ids)
                self.assertIn("mailto:rasgo.instruments@gmail.com", page.links)
                for credit in ("Basic Pitch", "librosa", "Audiveris", "MuseScore Studio", "FFmpeg"):
                    self.assertIn(credit, raw)
                for link in page.links:
                    url = urlsplit(link)
                    if url.scheme or url.netloc:
                        continue
                    target = filename if not url.path else url.path
                    self.assertTrue((SITE / target).is_file(), (filename, link))
                    if url.fragment:
                        if target == filename:
                            self.assertIn(url.fragment, page.ids, (filename, link))

    def test_no_premature_download_claim(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                raw = (SITE / filename).read_text(encoding="utf-8")
                self.assertNotIn("github.com/lucioaraujo/maravi", raw)
                self.assertNotIn("127.0.0.1", raw)


if __name__ == "__main__":
    unittest.main()
