"""Keep the next-work action visible on both result screens."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResultActionTests(unittest.TestCase):
    def test_next_action_follows_downloads(self):
        for template, target, label in (
            ("resultado.html", "/", "Transcrever outra música"),
            ("resultado_partitura.html", "/partitura", "Reconhecer outra partitura"),
        ):
            with self.subTest(template=template):
                html = (ROOT / "webapp" / "templates" / template).read_text(encoding="utf-8")
                self.assertIn(f'<a href="{target}', html)
                action_text = "{{ t('score_new') }}" if template == "resultado_partitura.html" else "{{ t('result_new') }}"
                self.assertIn(f'class="new-transcription">{action_text}', html)
                self.assertEqual(html.count('class="new-transcription"'), 1)
                self.assertLess(html.index('class="downloads"'), html.index('class="new-transcription"'))
                self.assertLess(html.index('class="new-transcription"'), html.index('class="result-note"'))

    def test_action_has_keyboard_and_mobile_styles(self):
        css = (ROOT / "webapp" / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".new-transcription:focus-visible", css)
        self.assertIn(".score-workspace .new-transcription { width: 100%; }", css)


if __name__ == "__main__":
    unittest.main()
