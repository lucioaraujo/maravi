"""Smoke tests locais: não executam inferência nem guardam áudio de teste."""
import io
import html
import json
from pathlib import Path
import re
import stat
import struct
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

from flask import render_template
from webapp.app import (EXPORT_TOKEN, app, default_export_directory,
                        extract_stereo_channel, use_solo_onset_filter)
from webapp.i18n import LANGUAGES, TEXT, display_key_name, frontend_text


class WebappTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_solo_voice_filter_requires_explicit_voice_and_isolated_source(self):
        self.assertTrue(use_solo_onset_filter("voice", True))
        for instrument, isolated in (("voice", False), ("melody", True),
                                     ("flute", True), ("piano", True)):
            with self.subTest(instrument=instrument, isolated=isolated):
                self.assertFalse(use_solo_onset_filter(instrument, isolated))

    def test_export_field_suggests_existing_personal_directory(self):
        with tempfile.TemporaryDirectory(prefix="maravi-home-test-") as folder:
            home = Path(folder)
            self.assertEqual(default_export_directory(home), str(home))
            documents = home / "Documents"
            documents.mkdir()
            self.assertEqual(default_export_directory(home), str(documents))
            with patch("webapp.app.default_export_directory", return_value=str(documents)):
                with app.test_request_context("/"):
                    html = render_template("_export_form.html", job_id="0123456789ab",
                                           export_token="test")
                    self.assertIn(f'value="{documents}"', html)
                    edited = render_template("_export_form.html", job_id="0123456789ab",
                                             export_token="test", entered_directory=str(home))
                    self.assertIn(f'value="{home}"', edited)

    def test_home_is_local_form(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(b"Transcrever uma melodia", response.data)
        self.assertIn(b"Canal esquerdo", response.data)
        self.assertIn("Este áudio já contém somente o instrumento escolhido".encode(), response.data)
        self.assertIn(b'href="/ajuda"', response.data)
        self.assertIn(b'class="workspace-layout"', response.data)
        self.assertIn(b'<body class="score-workspace">', response.data)
        self.assertIn(b'class="notation-example"', response.data)
        self.assertIn(b'class="field full notation-tools-heading"', response.data)
        self.assertEqual(response.data.count(b'class="field full notation-option"'), 3)
        self.assertIn(b"n\xc3\xa3o uma transcri\xc3\xa7\xc3\xa3o gerada", response.data)
        self.assertIn(b'value="piano_grand"', response.data)
        for control in (b'audio-input', b'audio_channel', b'score_instrument', b'source_isolated', b'mic-btn', b'bpm', b'tapBpm', b'join_equal_pitch',
                        b'phrase_downbeats', b'suppress_harmonic_spikes', b'submit-btn',
                        b'metro-bpm', b'metro-start', b'metro-use', b'audio-preview-area',
                        b'analyze-audio', b'audio-analysis-result'):
            self.assertIn(b'id="' + control + b'"', response.data)
        self.assertIn(b'/static/metronome.js', response.data)
        self.assertLess(response.data.index(b'id="audio-input"'),
                        response.data.index(b'id="bpm"'))
        self.assertLess(response.data.index(b'id="bpm"'),
                        response.data.index(b'id="work_title"'))
        metronome = self.client.get('/static/metronome.js')
        try:
            self.assertEqual(metronome.status_code, 200)
            self.assertIn(b'AudioContext', metronome.data)
        finally:
            metronome.close()
        css = self.client.get("/static/style.css")
        try:
            self.assertEqual(css.status_code, 200)
            self.assertEqual(css.headers["Cache-Control"], "no-store")
            self.assertIn(b"workspace-layout", css.data)
            self.assertIn(b"body.score-workspace", css.data)
            self.assertIn(b"#d5ddd6 25px 26px", css.data)
            self.assertIn(b'grid-template-areas: "form" "intro" "process"', css.data)
            self.assertIn(b".score-workspace .dropzone.dragover", css.data)
        finally:
            css.close()

    def test_home_language_covers_form_and_browser_messages(self):
        self.assertTrue(all(len(values) == len(LANGUAGES) for values in TEXT.values()))
        browser_keys = set()
        for filename in ("app.js", "metronome.js"):
            source = (Path(__file__).parents[1] / "webapp" / "static" / filename).read_text()
            browser_keys.update(re.findall(r'\btr\("([a-z_]+)"', source))
        browser_keys.update(("channel_mix", "channel_left", "channel_right",
                             "metro_playing", "metro_stopped"))
        self.assertFalse(browser_keys - frontend_text("pt").keys())
        for lang, heading, button in (
            ("en", "Transcribe a melody", "Record with microphone"),
            ("fr", "Transcrire une mélodie", "Enregistrer au microphone"),
            ("es", "Transcribir una melodía", "Grabar con el micrófono"),
        ):
            with self.subTest(lang=lang):
                html = self.client.get(f"/?lang={lang}").get_data(as_text=True)
                self.assertIn(f'<html lang="{lang}">', html)
                self.assertIn(heading, html)
                self.assertIn(button, html)
                self.assertIn(f'action="/transcrever?lang={lang}"', html)
                self.assertIn(f'href="/ajuda?lang={lang}"', html)
                self.assertIn('id="ui-strings-data"', html)
                self.assertIn('partial_language_notice', TEXT)
                error = self.client.post(f"/transcrever?lang={lang}", data={})
                self.assertEqual(error.status_code, 400)
                error_html = error.get_data(as_text=True)
                self.assertIn(f'href="/?lang={lang}"', error_html)
                self.assertIn({"en": "No audio file was uploaded.",
                               "fr": "Aucun fichier audio envoyé.",
                               "es": "No se envió ningún archivo de audio."}[lang], error_html)
        self.assertIn('<html lang="pt-BR">', self.client.get('/?lang=unknown').get_data(as_text=True))

    def test_score_upload_language_preserves_navigation_and_post(self):
        for lang, heading, page_label in (
            ("pt", "Do papel à escrita editável", "Página do PDF a reconhecer"),
            ("en", "From paper to editable notation", "PDF page to recognize"),
            ("fr", "Du papier à la notation modifiable", "Page du PDF à reconnaître"),
            ("es", "Del papel a la notación editable", "Página del PDF a reconocer"),
        ):
            with self.subTest(lang=lang):
                page = self.client.get(f"/partitura?lang={lang}")
                self.assertEqual(page.status_code, 200)
                html = page.get_data(as_text=True)
                self.assertIn(heading, html)
                self.assertIn(page_label, html)
                self.assertIn('https://github.com/Audiveris/audiveris', html)
                self.assertIn('https://github.com/musescore/MuseScore', html)
                action = '/reconhecer-partitura' + (f'?lang={lang}' if lang != 'pt' else '')
                self.assertIn(f'action="{action}"', html)
                error = self.client.post(action, data={})
                self.assertEqual(error.status_code, 400)
                back = '/partitura' + (f'?lang={lang}' if lang != 'pt' else '')
                error_html = error.get_data(as_text=True)
                self.assertIn(f'href="{back}"', error_html)
                self.assertIn({"pt": "Nenhuma partitura enviada.",
                               "en": "No score was uploaded.",
                               "fr": "Aucune partition envoyée.",
                               "es": "No se envió ninguna partitura."}[lang], error_html)

    def test_untranslated_technical_error_is_marked_as_portuguese(self):
        with app.test_request_context("/transcrever?lang=en"):
            error_html = render_template("erro.html", mensagem="Falha técnica de exemplo.")
        self.assertIn('lang="pt-BR">Falha técnica de exemplo.', error_html)
        self.assertIn('This technical detail may still appear in Portuguese.', error_html)

    def test_score_result_and_export_form_keep_selected_language(self):
        metadata = SimpleNamespace(original_filename="score.pdf", selected_page=1,
                                   pages=2, processed_pages=1)
        review = {"parts": 1, "measures": 2, "pitched_notes": 3, "rests": 1,
                  "checked_measures": 1, "skipped_measures": 1,
                  "warning_count": 1,
                  "warnings": [{"part": "P1", "measure": "2", "message": "Aviso técnico."}],
                  "limited": False}
        for lang, title in (("pt", "Rascunhos para conferir"),
                            ("en", "Drafts to review"),
                            ("fr", "Brouillons à vérifier"),
                            ("es", "Borradores para revisar")):
            with self.subTest(lang=lang), app.test_request_context(f"/reconhecer-partitura?lang={lang}"):
                html = render_template("resultado_partitura.html", metadata=metadata,
                                       job_id="0123456789ab", local_job_path="/tmp/test",
                                       export_token="test", structure_review=review)
                self.assertIn(title, html)
                self.assertIn('Aviso técnico.', html)
                self.assertNotIn("(s)", html)
                self.assertNotIn("(es)", html)
                query = f'?lang={lang}' if lang != 'pt' else ''
                self.assertIn(f'action="/exportar/0123456789ab{query}"', html)
                self.assertIn(f'href="/partitura{query}"', html)

    def test_export_confirmation_preserves_language_on_success_and_error(self):
        for lang, saved_title, failed_title in (
            ("pt", "Arquivos guardados", "Os arquivos não foram guardados"),
            ("en", "Files saved", "Files were not saved"),
            ("fr", "Fichiers enregistrés", "Les fichiers n'ont pas été enregistrés"),
            ("es", "Archivos guardados", "Los archivos no se guardaron"),
        ):
            with self.subTest(lang=lang), app.test_request_context(f"/exportar/0123456789ab?lang={lang}"):
                saved = render_template("exportado.html", saved_dir="/tmp/Maravi-test", job_id="0123456789ab")
                failed = render_template("exportado.html", diagnostic="Pasta inválida.",
                                         job_id="0123456789ab", export_token="test")
                self.assertIn(saved_title, saved)
                self.assertIn(failed_title, html.unescape(failed))
                self.assertIn('Pasta inválida.', failed)
                query = f'?lang={lang}' if lang != 'pt' else ''
                self.assertIn(f'action="/exportar/0123456789ab{query}"', failed)

    def test_audio_result_keeps_musical_caveats_in_four_languages(self):
        base = dict(work_title="Estudo", original_filename="estudo.wav", composer=None,
                    year=None, genre=None, score_instrument="flute", local_job_path="/tmp/job",
                    simplified_note_count=12, time_signature="4/4", display_bpm=90.0,
                    bpm_source="detectado", key_name="Sol menor", key_source="informado",
                    beat_count=16, solo_onsets_applied=False, onset_filtered=0,
                    part_name="Flauta", audio_channel="left", source_isolated=False,
                    excluded_low_notes=1, piano_lower_count=None, piano_upper_count=None,
                    piano_ignored_options=[], join_equal_pitch=False, phrase_downbeats=False,
                    suppress_harmonic_spikes=False, harmonic_spikes_corrected=0,
                    anacrusis_notes=0, key_confidence=0.7, key_runner_up="Si♭ maior",
                    joined_equal_pitch_count=0)
        for lang, caveat, key_name, runner in (
            ("pt", "não separa a flauta", "Sol menor", "Si♭ maior"),
            ("en", "does not isolate the flute", "G minor", "B♭ major"),
            ("fr", "sans isoler la flûte", "Sol mineur", "Si♭ majeur"),
            ("es", "no separa la flauta", "Sol menor", "Si♭ mayor"),
        ):
            with self.subTest(lang=lang), app.test_request_context(f"/transcrever?lang={lang}"):
                html = render_template("resultado.html", stats=SimpleNamespace(**base),
                                       job_id="0123456789ab", preview_available=True,
                                       export_token="test")
                self.assertIn(caveat, html)
                self.assertIn(f'<html lang="{lang if lang != "pt" else "pt-BR"}">', html)
                self.assertIn(key_name, html)
                self.assertIn(runner, html)
                self.assertIn('/preview/0123456789ab.svg', html)
                self.assertIn('0.7', html)
                self.assertIn(f'action="/exportar/0123456789ab{("?lang=" + lang) if lang != "pt" else ""}"', html)
        piano = {**base, "score_instrument": "piano_grand", "part_name": "Piano",
                 "audio_channel": "mix", "source_isolated": True,
                 "piano_lower_count": 0, "piano_upper_count": 5,
                 "piano_ignored_options": ["Solo ligado", "Anacruse"],
                 "key_confidence": None}
        with app.test_request_context('/transcrever?lang=en'):
            html = render_template("resultado.html", stats=SimpleNamespace(**piano),
                                   job_id="0123456789ab", preview_available=False,
                                   export_token="test")
        self.assertIn('Two-staff piano', html)
        self.assertIn('Legato solo, Pickup', html)
        self.assertIn('does not invent a left hand', html)
        self.assertIn('does not yet display two staves', html)
        voice = {**base, "score_instrument": "voice", "part_name": "Voz",
                 "solo_onsets_applied": True, "onset_filtered": 2,
                 "join_equal_pitch": True, "joined_equal_pitch_count": 3,
                 "phrase_downbeats": True, "suppress_harmonic_spikes": True,
                 "harmonic_spikes_corrected": 1, "anacrusis_notes": 2}
        with app.test_request_context('/transcrever?lang=en'):
            html = render_template("resultado.html", stats=SimpleNamespace(**voice),
                                   job_id="0123456789ab", preview_available=False,
                                   export_token="test")
        for phrase in ("filter may also omit real notes", "real repeated attacks",
                       "Fermatas are interpretation suggestions",
                       "does not yet confirm the fundamental", "Configured pickup"):
            self.assertIn(phrase, html)
        self.assertEqual(display_key_name("en", "Fá♯ maior"), "F♯ major")
        self.assertEqual(display_key_name("en", "unrecognized label"), "unrecognized label")

    def test_preview_errors_use_requested_language(self):
        for lang, missing, bad_format in (
            ("pt", "Escolha um áudio antes da análise.", "Formato de áudio não suportado."),
            ("en", "Choose an audio file before analysis.", "Unsupported audio format."),
            ("fr", "Choisissez un fichier audio avant l'analyse.", "Format audio non pris en charge."),
            ("es", "Elija un audio antes del análisis.", "Formato de audio no admitido."),
        ):
            with self.subTest(lang=lang):
                response = self.client.post(f"/analisar-audio?lang={lang}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"], missing)
                response = self.client.post(f"/analisar-audio?lang={lang}",
                                            data={"audio": (io.BytesIO(b"x"), "test.txt")})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"], bad_format)

    def test_tutorial_is_available(self):
        response = self.client.get("/ajuda")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<body class="score-workspace">', response.data)
        for anchor in (b'gravacao', b'pistas', b'processamento', b'revisao'):
            self.assertIn(b'href="#' + anchor + b'"', response.data)
            self.assertIn(b'id="' + anchor + b'"', response.data)
        self.assertIn(b"Da grava", response.data)
        self.assertIn(b"Escrita, interpreta", response.data)

    def test_tutorial_four_languages_without_claiming_full_app_translation(self):
        cases = (
            ("pt", "pt-BR", "Da gravação à partitura", "Baixe e revise"),
            ("en", "en", "How to use Maravi", "Download and review"),
            ("fr", "fr", "Utiliser Maravi", "Téléchargez et vérifiez"),
            ("es", "es", "Cómo usar Maravi", "Descargue y revise"),
        )
        for lang, html_lang, heading, review in cases:
            with self.subTest(lang=lang):
                response = self.client.get(f"/ajuda?lang={lang}")
                self.assertEqual(response.status_code, 200)
                self.assertIn(f'<html lang="{html_lang}">'.encode(), response.data)
                self.assertIn(heading.encode(), response.data)
                self.assertIn(review.encode(), response.data)
                self.assertIn(f'href="/ajuda?lang={lang}"'.encode(), response.data)
                self.assertIn(b'aria-current="page"', response.data)
        self.assertIn(b'<html lang="pt-BR">', self.client.get('/ajuda?lang=invalid').data)

    def test_missing_audio_is_readable_error(self):
        response = self.client.post("/transcrever")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'<body class="score-workspace">', response.data)
        self.assertIn(b"Nenhum arquivo", response.data)

    def test_bad_fields_do_not_create_a_job(self):
        for fields in ({"bpm": "abc"}, {"bpm": "nan"}, {"tap_count": "17"},
                       {"anacrusis_notes": "-2"}, {"time_signature": "0/4"},
                       {"time_signature": "4/zero"}):
            with self.subTest(fields=fields):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "teste.wav"), **fields},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Confira os campos", response.data)

    def test_download_rejects_unknown_job_and_format(self):
        for url in ("/download/../mid", "/download/0123456789ab/mid",
                    "/download/0123456789ab/musicxml", "/download/0123456789ab/pdf",
                    "/preview/0123456789ab.svg", "/preview/invalid.svg"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_export_pair_to_existing_local_directory_without_overwrite(self):
        job_id = "0123456789ab"
        with tempfile.TemporaryDirectory(prefix="maravi-export-test-") as folder:
            base = Path(folder)
            jobs = base / "jobs"
            job = jobs / job_id
            job.mkdir(parents=True)
            (job / "resultado.musicxml").write_bytes(b"<score/>")
            (job / "resultado.mid").write_bytes(b"MThd-test")
            destination = base / "partituras"
            destination.mkdir()
            (destination / "ja-existente.txt").write_text("intacto", encoding="utf-8")
            with patch("webapp.app.JOBS_DIR", jobs):
                response = self.client.post(
                    f"/exportar/{job_id}",
                    data={"export_token": EXPORT_TOKEN, "destination": str(destination)},
                )
                self.assertEqual(response.status_code, 200)
                saved = destination / f"Maravi-{job_id}"
                self.assertEqual((saved / "resultado.musicxml").read_bytes(), b"<score/>")
                self.assertEqual((saved / "resultado.mid").read_bytes(), b"MThd-test")
                self.assertEqual((destination / "ja-existente.txt").read_text(), "intacto")
                self.assertEqual((job / "resultado.musicxml").read_bytes(), b"<score/>")
                self.assertIn(str(saved).encode(), response.data)

                repeated = self.client.post(
                    f"/exportar/{job_id}?lang=fr",
                    data={"export_token": EXPORT_TOKEN, "destination": str(destination)},
                )
                self.assertEqual(repeated.status_code, 409)
                self.assertEqual((saved / "resultado.mid").read_bytes(), b"MThd-test")
                self.assertIn(b"Maravi n&#39;a pas pu enregistrer les fichiers", repeated.data)
                self.assertIn("Détail technique".encode(), repeated.data)
                self.assertIn("Esta subpasta Maravi já existe no destino".encode(), repeated.data)
                self.assertIn(b'name="destination"', repeated.data)
                self.assertIn(str(destination).encode(), repeated.data)

    def test_export_copy_error_removes_only_its_partial_output(self):
        job_id = "0123456789ab"
        with tempfile.TemporaryDirectory(prefix="maravi-export-test-") as folder:
            base = Path(folder)
            jobs = base / "jobs"
            job = jobs / job_id
            job.mkdir(parents=True)
            (job / "resultado.musicxml").write_bytes(b"xml")
            (job / "resultado.mid").write_bytes(b"mid")
            destination = base / "partituras"
            destination.mkdir()
            (destination / "intacto.txt").write_text("original", encoding="utf-8")

            def fail_during_second_copy(source, output, length):
                if source.name.endswith(".mid"):
                    output.write(b"parcial")
                    raise OSError("disco cheio de teste")
                output.write(source.read())

            with patch("webapp.app.JOBS_DIR", jobs), patch(
                "webapp.app.shutil.copyfileobj", side_effect=fail_during_second_copy
            ):
                response = self.client.post(
                    f"/exportar/{job_id}",
                    data={"export_token": EXPORT_TOKEN, "destination": str(destination)},
                )
            self.assertEqual(response.status_code, 500)
            self.assertIn(b'name="destination"', response.data)
            self.assertFalse((destination / f"Maravi-{job_id}").exists())
            self.assertEqual((destination / "intacto.txt").read_text(), "original")
            self.assertEqual((job / "resultado.musicxml").read_bytes(), b"xml")
            self.assertEqual((job / "resultado.mid").read_bytes(), b"mid")

    def test_export_rejects_cross_site_remote_and_unsafe_destinations(self):
        job_id = "0123456789ab"
        with tempfile.TemporaryDirectory(prefix="maravi-export-test-") as folder:
            base = Path(folder)
            jobs = base / "jobs"
            job = jobs / job_id
            job.mkdir(parents=True)
            (job / "resultado.musicxml").write_bytes(b"xml")
            (job / "resultado.mid").write_bytes(b"mid")
            with patch("webapp.app.JOBS_DIR", jobs):
                url = f"/exportar/{job_id}"
                self.assertEqual(self.client.post(url, data={"destination": str(base)}).status_code, 403)
                self.assertEqual(self.client.post(
                    url, data={"destination": str(base), "export_token": EXPORT_TOKEN},
                    environ_overrides={"REMOTE_ADDR": "192.0.2.1"},
                ).status_code, 403)
                self.assertEqual(self.client.post(
                    url, data={"destination": str(base), "export_token": EXPORT_TOKEN},
                    base_url="http://example.com",
                ).status_code, 403)
                for destination in (str(job), "relative/path", str(base / "missing")):
                    with self.subTest(destination=destination):
                        response = self.client.post(
                            url, data={"destination": destination, "export_token": EXPORT_TOKEN},
                        )
                        self.assertEqual(response.status_code, 400)
                self.assertEqual(sorted(path.name for path in base.iterdir()), ["jobs"])
                (job / "resultado.mid").unlink()
                self.assertEqual(self.client.post(
                    url, data={"destination": str(base), "export_token": EXPORT_TOKEN},
                ).status_code, 404)

    def test_oversized_upload_has_readable_error(self):
        original = app.config["MAX_CONTENT_LENGTH"]
        try:
            app.config["MAX_CONTENT_LENGTH"] = 128
            response = self.client.post(
                "/transcrever",
                data={"audio": (io.BytesIO(b"x" * 256), "teste.wav")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 413)
            self.assertIn(b"Arquivo grande demais", response.data)
        finally:
            app.config["MAX_CONTENT_LENGTH"] = original

    def test_failed_mic_conversion_discards_only_its_job(self):
        with tempfile.TemporaryDirectory(prefix="maravi-test-") as folder:
            jobs_dir = Path(folder)
            with patch("webapp.app.JOBS_DIR", jobs_dir), patch(
                "webapp.app.convert_to_wav", side_effect=RuntimeError("falha de teste")
            ):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "gravacao.webm"), "source": "mic"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 500)
            self.assertIn(b"falha de teste", response.data)
            self.assertEqual(list(jobs_dir.iterdir()), [])

    def test_channel_choice_extracts_only_requested_side(self):
        with tempfile.TemporaryDirectory(prefix="maravi-channel-test-") as folder:
            source = Path(folder) / "stereo.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(struct.pack("<hh", 1000, -2000) * 800)
            for channel, positive in (("left", True), ("right", False)):
                selected = Path(folder) / f"{channel}.wav"
                extract_stereo_channel(source, selected, channel)
                with wave.open(str(selected), "rb") as wav:
                    self.assertEqual(wav.getnchannels(), 1)
                    self.assertEqual(wav.getframerate(), 44100)
                    sample = struct.unpack("<h", wav.readframes(1))[0]
                    self.assertEqual(sample > 0, positive)
            self.assertEqual(source.read_bytes()[:4], b"RIFF")
            with self.assertRaisesRegex(ValueError, "dois canais"):
                extract_stereo_channel(Path(folder) / "left.wav", Path(folder) / "wrong.wav", "right")

    def test_left_channel_web_flow_preserves_original_and_does_not_claim_flute(self):
        with tempfile.TemporaryDirectory(prefix="maravi-channel-test-") as folder:
            source = Path(folder) / "source.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(struct.pack("<hh", 1000, -2000) * 800)
            source_bytes = source.read_bytes()
            jobs_dir = Path(folder) / "jobs"
            jobs_dir.mkdir()
            called = []

            def check_pipeline(audio_path, **kwargs):
                called.append(Path(audio_path).name)
                self.assertEqual(Path(audio_path).name, "entrada_canal_left.wav")
                self.assertEqual((Path(audio_path).parent / "entrada.wav").read_bytes(), source_bytes)
                self.assertEqual(kwargs["midi_program"], 0)
                self.assertIsNone(kwargs["preserve_low_register_from"])
                raise RuntimeError("fim do teste antes da inferência")

            with patch("webapp.app.JOBS_DIR", jobs_dir), patch(
                "transcribe_monophonic.run_pipeline", side_effect=check_pipeline
            ):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(source_bytes), "entrada.wav"),
                          "audio_channel": "left"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 500)
            self.assertEqual(called, ["entrada_canal_left.wav"])
            self.assertEqual(list(jobs_dir.iterdir()), [])
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_invalid_channel_does_not_create_job(self):
        with tempfile.TemporaryDirectory(prefix="maravi-channel-test-") as folder:
            with patch("webapp.app.JOBS_DIR", Path(folder)):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "teste.wav"),
                          "audio_channel": "center"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_invalid_instrument_does_not_create_job(self):
        with tempfile.TemporaryDirectory(prefix="maravi-instrument-test-") as folder:
            with patch("webapp.app.JOBS_DIR", Path(folder)):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "teste.wav"),
                          "score_instrument": "unknown"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_flute_with_no_notes_in_range_reports_error_without_retry(self):
        from transcribe_monophonic import NoNotesInRangeError

        with tempfile.TemporaryDirectory(prefix="maravi-flute-range-test-") as folder:
            with patch("webapp.app.JOBS_DIR", Path(folder)), patch(
                "transcribe_monophonic.run_pipeline",
                side_effect=NoNotesInRangeError("Nenhuma nota detectada ficou no registro escolhido."),
            ) as pipeline, patch("webapp.app.convert_to_wav") as converter:
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "flauta.wav"),
                          "score_instrument": "flute"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 422)
            self.assertIn(b"Nenhuma nota detectada", response.data)
            self.assertEqual(pipeline.call_count, 1)
            converter.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_audio_preview_reports_without_leaving_a_job(self):
        report = {"duration_seconds": 3, "channels": 1, "sample_seconds": 3,
                  "selected_channel": "mix", "bpm": None, "tempo_regularity": None,
                  "key_name": None, "key_runner_up": None, "key_ambiguous": True,
                  "instrument": None, "meter": None}
        with tempfile.TemporaryDirectory(prefix="maravi-analysis-test-") as folder:
            jobs = Path(folder)

            def fake_analyzer(command, **_kwargs):
                self.assertEqual(Path(command[3]).read_bytes(), b"audio de teste")
                self.assertEqual(command[-1], "mix")
                return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

            with patch("webapp.app.JOBS_DIR", jobs), patch(
                "webapp.app.subprocess.run", side_effect=fake_analyzer
            ):
                response = self.client.post(
                    "/analisar-audio",
                    data={"audio": (io.BytesIO(b"audio de teste"), "teste.wav")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), report)
            self.assertEqual(list(jobs.iterdir()), [])

    def test_audio_preview_rejects_invalid_input_or_busy_slot(self):
        from webapp.app import AUDIO_SLOT

        with tempfile.TemporaryDirectory(prefix="maravi-analysis-test-") as folder, patch(
            "webapp.app.JOBS_DIR", Path(folder)
        ):
            self.assertEqual(self.client.post("/analisar-audio").status_code, 400)
            self.assertEqual(self.client.post(
                "/analisar-audio", data={"audio": (io.BytesIO(b"x"), "teste.txt")},
                content_type="multipart/form-data",
            ).status_code, 400)
            self.assertTrue(AUDIO_SLOT.acquire(blocking=False))
            try:
                response = self.client.post(
                    "/analisar-audio", data={"audio": (io.BytesIO(b"x"), "teste.wav")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 503)
            finally:
                AUDIO_SLOT.release()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_audio_preview_global_upload_limit_returns_json(self):
        original = app.config["MAX_CONTENT_LENGTH"]
        try:
            app.config["MAX_CONTENT_LENGTH"] = 128
            response = self.client.post(
                "/analisar-audio", data={"audio": (io.BytesIO(b"x" * 256), "teste.wav")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 413)
            self.assertIn("50 MB", response.get_json()["error"])
        finally:
            app.config["MAX_CONTENT_LENGTH"] = original

    def test_audio_preview_stream_limit_cleans_partial_upload(self):
        with tempfile.TemporaryDirectory(prefix="maravi-analysis-test-") as folder, patch(
            "webapp.app.JOBS_DIR", Path(folder)
        ), patch("webapp.app.MAX_PREVIEW_BYTES", 4), patch(
            "webapp.app.subprocess.run"
        ) as analyzer:
            response = self.client.post(
                "/analisar-audio", data={"audio": (io.BytesIO(b"12345"), "teste.wav")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 413)
            self.assertEqual(list(Path(folder).iterdir()), [])
            analyzer.assert_not_called()

    def test_result_and_downloads_without_running_inference(self):
        class Midi:
            def write(self, path):
                Path(path).write_bytes(b"MIDI-DE-TESTE")

        fake_result = {
            "midi": Midi(), "raw_note_count": 1, "melody_note_count": 1,
            "simplified_note_count": 1, "beat_count": 2, "display_bpm": 100,
            "bpm_source": "detectado", "beats_per_measure": 4, "beat_unit": 4,
            "key": None, "key_source": "indisponivel", "tap_info": None,
            "beat_times": [0, 0.6], "beat_divisions": [2], "downbeat_time": 0,
            "simplified_melody": [], "key_fifths": 0, "key_mode": "major",
            "excluded_low_notes": 2,
            "piano_notes": [{"start": 0.0, "end": 0.6, "pitch": 60, "amplitude": 0.8}],
            "piano_midi": Midi(),
        }

        fake_xml = (
            '<score-partwise version="4.0"><part id="P1"><measure number="1">'
            '<attributes><divisions>24</divisions><key><fifths>0</fifths></key>'
            '<time><beats>4</beats><beat-type>4</beat-type></time></attributes>'
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>24</duration><type>quarter</type></note>'
            '</measure></part></score-partwise>'
        )

        score_labels = []

        def fake_musicxml(*_args, **kwargs):
            self.assertTrue(kwargs["readable_notation"])
            self.assertTrue(kwargs["phrase_downbeats"])
            score_labels.append((kwargs["part_name"], kwargs["instrument_name"],
                                 kwargs["midi_program"]))
            Path(kwargs["path"]).write_text(fake_xml, encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="maravi-test-") as folder:
            with patch("webapp.app.JOBS_DIR", Path(folder)), patch(
                "transcribe_monophonic.run_pipeline", return_value=fake_result
            ) as run_pipeline_mock, patch("musicxml_writer.write_musicxml", side_effect=fake_musicxml):
                response = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "teste.wav"),
                          "work_title": "Teste", "join_equal_pitch": "on",
                          "phrase_downbeats": "on", "suppress_harmonic_spikes": "on"},
                    content_type="multipart/form-data",
                )
                self.assertTrue(run_pipeline_mock.call_args.kwargs["join_equal_pitch"])
                self.assertTrue(run_pipeline_mock.call_args.kwargs["suppress_harmonic_spikes"])
                self.assertEqual(run_pipeline_mock.call_args.kwargs["midi_program"], 0)
                self.assertIsNone(run_pipeline_mock.call_args.kwargs["preserve_low_register_from"])
                self.assertIsNone(run_pipeline_mock.call_args.kwargs["minimum_pitch"])
                self.assertEqual(score_labels[-1], ("Melodia", None, None))
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"n\xc3\xa3o uma extra\xc3\xa7\xc3\xa3o", response.data)
                self.assertIn(b'<body class="score-workspace">', response.data)
                self.assertIn("Censo crítico".encode("utf-8"), response.data)
                self.assertIn("não confirma que as notas estejam corretas".encode("utf-8"), response.data)
                self.assertIn("símbolos de nota com altura".encode("utf-8"), response.data)
                match = re.search(rb"/download/([0-9a-f]{12})/mid", response.data)
                self.assertIsNotNone(match)
                job_id = match.group(1).decode("ascii")
                mid_response = self.client.get(f"/download/{job_id}/mid")
                xml_response = self.client.get(f"/download/{job_id}/musicxml")
                try:
                    self.assertEqual(mid_response.data, b"MIDI-DE-TESTE")
                    self.assertEqual(xml_response.data, fake_xml.encode("utf-8"))
                finally:
                    mid_response.close()
                    xml_response.close()
                self.assertIn(f'/preview/{job_id}.svg'.encode(), response.data)
                preview = self.client.get(f"/preview/{job_id}.svg")
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.mimetype, "image/svg+xml")
                self.assertIn(b"Compasso 1", preview.data)
                self.assertEqual(preview.headers["X-Content-Type-Options"], "nosniff")
                preview.close()
                self.assertTrue((Path(folder) / job_id / "entrada.wav").is_file())
                self.assertEqual(stat.S_IMODE((Path(folder) / job_id).stat().st_mode) & 0o077, 0)
                self.assertIn(str(Path(folder) / job_id).encode(), response.data)
                self.assertIn(f'action="/exportar/{job_id}"'.encode(), response.data)

                piano = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "piano.wav"),
                          "score_instrument": "piano", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(piano.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["midi_program"], 0)
                self.assertIsNone(run_pipeline_mock.call_args.kwargs["preserve_low_register_from"])
                self.assertIsNone(run_pipeline_mock.call_args.kwargs["minimum_pitch"])
                self.assertEqual(score_labels[-1], ("Piano", "Piano", 1))
                self.assertIn(b"n\xc3\xa3o reconstr\xc3\xb3i acordes", piano.data)

                piano_grand = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "piano_duas_pautas.wav"),
                          "score_instrument": "piano_grand", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(piano_grand.status_code, 200)
                self.assertTrue(run_pipeline_mock.call_args.kwargs["piano_two_staves"])
                self.assertIn(b"duas pautas", piano_grand.data)
                self.assertIn(b"Escrita por frases", piano_grand.data)
                self.assertIn(b"pr\xc3\xa9via no navegador ainda n\xc3\xa3o l\xc3\xaa duas pautas", piano_grand.data)
                self.assertIn(b"Nenhuma nota foi detectada no registro inferior", piano_grand.data)
                self.assertIn(b"hip\xc3\xb3tese polif\xc3\xb4nica", piano_grand.data)
                piano_grand_match = re.search(rb"/download/([0-9a-f]{12})/musicxml", piano_grand.data)
                self.assertIsNotNone(piano_grand_match)
                piano_grand_xml = self.client.get(
                    f"/download/{piano_grand_match.group(1).decode()}/musicxml"
                )
                self.assertIn(b"<staves>2</staves>", piano_grand_xml.data)
                piano_grand_xml.close()

                flute_mix = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "mistura.wav"),
                          "score_instrument": "flute", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(flute_mix.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 59)
                self.assertIsNone(run_pipeline_mock.call_args.kwargs["preserve_low_register_from"])
                self.assertIn("não separa".encode(), flute_mix.data)
                self.assertIn(b"2 candidatas abaixo de si3", flute_mix.data)

                voice_default = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "voz-com-acompanhamento.wav"),
                          "score_instrument": "voice", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(voice_default.status_code, 200, voice_default.data.decode("utf-8", "replace"))
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 55)
                self.assertIn("Registro vocal Médio".encode(), voice_default.data)
                self.assertIn("não identifica quais notas restantes são da voz".encode(), voice_default.data)

                voice_low = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "voz-grave.wav"),
                          "score_instrument": "voice", "voice_register": "low",
                          "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(voice_low.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 48)

                voice_high = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "voz-aguda.wav"),
                          "score_instrument": "voice", "voice_register": "high",
                          "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(voice_high.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 60)

                flute_declared = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "flauta.wav"),
                          "score_instrument": "flute", "source_isolated": "on",
                          "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(flute_declared.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["midi_program"], 73)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["preserve_low_register_from"], 59)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 59)
                self.assertEqual(score_labels[-1], ("Flauta", "Flute", 74))

                isolated = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(b"test"), "flauta.wav"),
                          "flute_only_source": "on", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(isolated.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["midi_program"], 73)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["preserve_low_register_from"], 59)
                self.assertEqual(run_pipeline_mock.call_args.kwargs["minimum_pitch"], 59)
                self.assertEqual(score_labels[-1], ("Flauta", "Flute", 74))

                stereo_bytes = io.BytesIO()
                with wave.open(stereo_bytes, "wb") as wav:
                    wav.setnchannels(2)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(struct.pack("<hh", 1000, -2000) * 800)
                selected = self.client.post(
                    "/transcrever",
                    data={"audio": (io.BytesIO(stereo_bytes.getvalue()), "estereo.wav"),
                          "audio_channel": "left", "phrase_downbeats": "on"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(selected.status_code, 200)
                self.assertEqual(run_pipeline_mock.call_args.args[0].name, "entrada_canal_left.wav")
                self.assertIn(b"canal esquerdo", selected.data)
                self.assertIn(b"demais instrumentos presentes", selected.data)
                self.assertEqual(score_labels[-1], ("Melodia", None, None))


if __name__ == "__main__":
    unittest.main()
