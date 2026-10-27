"""Checks for the public website (not the local Flask application), 2026-10-27."""

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlsplit


SITE = Path(__file__).resolve().parents[1] / "website"
PAGES = {"index.html": "pt-BR", "en.html": "en", "fr.html": "fr", "es.html": "es"}
INSTALL_PAGES = {"instalacao.html": "pt-BR", "instalacao-en.html": "en",
                 "instalacao-fr.html": "fr", "instalacao-es.html": "es"}
RELEASES = "https://github.com/lucioaraujo/maravi/releases/latest"
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
    def check_links(self, filename, raw, page):
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = filename if not url.path else url.path
            self.assertTrue((SITE / target).is_file(), (filename, link))
            if url.fragment and target == filename:
                self.assertIn(url.fragment, page.ids, (filename, link))

    def test_four_languages_and_local_links(self):
        for filename, language in {**PAGES, **INSTALL_PAGES}.items():
            with self.subTest(filename=filename):
                raw = (SITE / filename).read_text(encoding="utf-8")
                page = Page()
                page.feed(raw)
                self.assertEqual(page.language, language)
                # the RASGO family strip, above the page's own header
                self.assertIn('class="rasgo-strip"', raw)
                self.assertIn("https://rasgoinstruments.arquiviagem.net/", raw)
                # contact without mailto: the address is assembled by the script
                self.assertNotIn("mailto:", raw)
                # no stray regex backreference, every list closed (a "\\1" once
                # replaced a </ul> on the published pages, 2026-10-27)
                self.assertNotRegex(raw, r"\\[0-9]")
                for tag in ("ul", "ol", "section", "article", "div"):
                    self.assertEqual(raw.count("<%s" % tag), raw.count("</%s>" % tag), (filename, tag))
                self.assertIn("assets/contact.js", page.links)
                self.check_links(filename, raw, page)

    def test_about_pages(self):
        for filename, language in PAGES.items():
            with self.subTest(filename=filename):
                raw = (SITE / filename).read_text(encoding="utf-8")
                page = Page()
                page.feed(raw)
                self.assertEqual(page.current_languages, 1)
                self.assertIn(ABOUT_IDS[filename], page.ids)
                self.assertIn(CONTACT_IDS[filename], page.ids)
                self.assertIn("data-contact-trigger", raw)
                self.assertIn(RELEASES, page.links)
                for credit in ("Basic Pitch", "librosa", "Audiveris", "MuseScore Studio", "FFmpeg"):
                    self.assertIn(credit, raw)
                self.assertNotIn("127.0.0.1", raw)

    def test_install_pages_follow_install_md(self):
        for filename in INSTALL_PAGES:
            with self.subTest(filename=filename):
                raw = (SITE / filename).read_text(encoding="utf-8")
                self.assertIn("maravi-0.1.1-linux-x86_64.tar.xz", raw)
                self.assertIn("ffmpeg", raw)
        result = subprocess.run([sys.executable, "-B", str(SITE / "gerar_instalacao.py")],
                                capture_output=True, text=True, timeout=30, cwd=SITE)
        self.assertEqual(result.returncode, 0, result.stderr)
        seo = subprocess.run([sys.executable, "-B", str(SITE / "seo.py"), "--verificar"],
                             capture_output=True, text=True, timeout=30, cwd=SITE)
        self.assertEqual(seo.returncode, 0, seo.stdout + seo.stderr)

    def test_free_embedded_fonts_only(self):
        css = (SITE / "styles.css").read_text(encoding="utf-8")
        for named in ("system-ui", "Georgia", "Segoe", "Helvetica", "Arial"):
            self.assertNotIn(named, css)
        for font in ("Fraunces.woff2", "WorkSans.woff2", "JetBrainsMono.woff2", "OFL.txt"):
            self.assertTrue((SITE / "assets" / "fonts" / font).is_file(), font)


if __name__ == "__main__":
    unittest.main()
