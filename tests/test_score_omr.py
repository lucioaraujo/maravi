"""Contrato leve do caminho PDF/imagem, sem executar OMR pesado."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from werkzeug.datastructures import FileStorage

from webapp.app import OMR_SLOT, app
from score_omr import (ScoreInputError, ScoreToolError, _image_command, _run, available_tools,
                       prepare_score_source, recognize_score,
                       review_musicxml_structure, save_score_input)


PDF = b"%PDF-1.4\nrascunho de teste"
PNG = b"\x89PNG\r\n\x1a\nrascunho de teste"
JPG = b"\xff\xd8\xffrascunho de teste"
TIFF = b"II*\x00rascunho de teste"
WEBP = b"RIFF\x12\x00\x00\x00WEBPVP8 "
BMP = b"BMrascunho de teste"
GIF = b"GIF89arascunho de teste"
HEIC = b"\x00\x00\x00\x18ftypheicrascunho"
HEIF = b"\x00\x00\x00\x18ftypmif1rascunho"
AVIF = b"\x00\x00\x00\x18ftypavifrascunho"


def upload(data, filename):
    return FileStorage(stream=io.BytesIO(data), filename=filename)


def fake_audiveris_book(output_dir):
    book = output_dir / "partitura_original"
    book.mkdir(parents=True)
    with zipfile.ZipFile(book / "partitura_original.omr", "w") as archive:
        archive.writestr("book.xml", "<book/>")
    with zipfile.ZipFile(book / "partitura_original.mxl", "w") as archive:
        archive.writestr("score.xml", '<score-partwise version="4.0"/>')


class ScoreOmrTests(unittest.TestCase):
    def test_structure_review_reports_only_checkable_measures(self):
        score = ET.parse(Path(__file__).parent / "fixtures/omr_smoke.musicxml").getroot()
        clean = review_musicxml_structure(score)
        self.assertEqual(clean["parts"], 1)
        self.assertEqual(clean["measures"], 8)
        self.assertEqual(clean["checked_measures"], 6)
        self.assertEqual(clean["warning_count"], 0)

        second = score.find(".//measure[@number='2']")
        second.find("note/duration").text = "2"
        score.find(".//measure[@number='3']").set("number", "5")
        flagged = review_musicxml_structure(score)
        self.assertEqual(flagged["warning_count"], 2)
        self.assertTrue(any("Duração escrita" in item["message"] for item in flagged["warnings"]))
        self.assertTrue(any("Numeração salta" in item["message"] for item in flagged["warnings"]))

        ET.SubElement(second, "backup")
        skipped = review_musicxml_structure(score)
        self.assertEqual(skipped["warning_count"], 1)
        self.assertEqual(skipped["checked_measures"], 5)

    def test_structure_review_marks_empty_omr_without_approving_it(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1">'
                             '<note><rest/><duration>4</duration></note>'
                             '</measure></part></score-partwise>')
        report = review_musicxml_structure(root)
        self.assertEqual(report["pitched_notes"], 0)
        self.assertEqual(report["warning_count"], 1)
        self.assertIn("Nenhuma nota", report["warnings"][0]["message"])

    def test_audiveris_runs_headless_with_bounded_heap(self):
        with patch.dict("score_omr.os.environ", {}, clear=True), \
                patch("score_omr.subprocess.Popen") as launch:
            launch.return_value.wait.return_value = 0
            _run([sys.executable, "-version"], timeout=1, audiveris_tool=True)
            options = launch.call_args.kwargs["env"]["JAVA_TOOL_OPTIONS"]
            self.assertIn("-Djava.awt.headless=true", options)
            self.assertIn("-Xmx1536m", options)

        with patch.dict("score_omr.os.environ", {"JAVA_TOOL_OPTIONS": "-Xmx2048m"}, clear=True), \
                patch("score_omr.subprocess.Popen") as launch:
            launch.return_value.wait.return_value = 0
            _run([sys.executable, "-version"], timeout=1, audiveris_tool=True)
            options = launch.call_args.kwargs["env"]["JAVA_TOOL_OPTIONS"]
            self.assertIn("-Xmx2048m", options)
            self.assertIn("-Djava.awt.headless=true", options)
            self.assertNotIn("-Xmx1536m", options)

    def test_detects_official_linux_binary_and_respects_configured_path(self):
        with tempfile.TemporaryDirectory() as folder:
            installed = Path(folder) / "Audiveris"
            installed.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            installed.chmod(0o755)
            with patch.dict("score_omr.os.environ", {}, clear=True), \
                    patch("score_omr.shutil.which", return_value=None), \
                    patch("score_omr.AUDIVERIS_LINUX_BIN", installed):
                self.assertEqual(available_tools()[0], str(installed))
            with patch.dict("score_omr.os.environ", {"MARAVI_AUDIVERIS_BIN": str(installed)}), \
                    patch("score_omr.shutil.which", return_value=None):
                self.assertEqual(available_tools()[0], str(installed))
            installed.chmod(0o644)
            with patch.dict("score_omr.os.environ", {"MARAVI_AUDIVERIS_BIN": str(installed)}), \
                    patch("score_omr.shutil.which", return_value=None):
                self.assertIsNone(available_tools()[0])

    def test_musescore_override_is_explicit_and_image_commands_are_portable(self):
        with tempfile.TemporaryDirectory() as folder:
            installed = Path(folder) / "MuseScore4.exe"
            installed.write_text("test", encoding="utf-8")
            installed.chmod(0o755)
            with patch.dict("score_omr.os.environ", {"MARAVI_MUSESCORE_BIN": str(installed)}), \
                    patch("score_omr.shutil.which", return_value=None):
                self.assertEqual(available_tools()[1], str(installed))
            installed.chmod(0o644)
            with patch.dict("score_omr.os.environ", {"MARAVI_MUSESCORE_BIN": str(installed)}), \
                    patch("score_omr.shutil.which", return_value=None):
                self.assertIsNone(available_tools()[1])
        with patch("score_omr.shutil.which", side_effect=lambda name: "/tools/magick" if name == "magick" else None):
            self.assertEqual(_image_command("identify", platform_name="nt"), ["/tools/magick", "identify"])
            self.assertEqual(_image_command("convert", platform_name="nt"), ["/tools/magick", "convert"])
        with patch("score_omr.shutil.which", side_effect=lambda name: "C:/Windows/System32/convert.exe" if name == "convert" else None):
            self.assertIsNone(_image_command("convert", platform_name="nt"))
        with patch("score_omr.shutil.which", side_effect=lambda name: "/usr/bin/identify" if name == "identify" else None):
            self.assertEqual(_image_command("identify", platform_name="posix"), ["identify"])

    def test_score_page_advertises_only_available_tools(self):
        client = app.test_client()
        with patch("webapp.app.available_tools", return_value=(None, sys.executable)):
            response = client.get("/partitura")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'.pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,.gif,.heic,.heif,.avif', response.data)
        self.assertIn(b'name="pdf_page"', response.data)
        self.assertIn(b'Audiveris', response.data)
        self.assertIn(b'GNU AGPLv3', response.data)
        self.assertIn(b'disabled', response.data)

    def test_supported_formats_and_provenance(self):
        samples = [(PDF, "score.pdf", "Pages: 2\n"),
                   (PNG, "score.png", "1200 800\n"),
                   (JPG, "score.jpg", "1200 800\n"),
                   (JPG, "score.jpeg", "1200 800\n"),
                   (TIFF, "score.tif", "1200 800\n"),
                   (TIFF, "score.tiff", "1200 800\n"),
                   (WEBP, "score.webp", "1200 800\n"),
                   (BMP, "score.bmp", "1200 800\n"),
                   (GIF, "score.gif", "1200 800\n"),
                   (HEIC, "score.heic", "1200 800\n"),
                   (HEIF, "score.heif", "1200 800\n"),
                   (AVIF, "score.avif", "1200 800\n")]
        for data, name, output in samples:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                with patch("score_omr.subprocess.run") as tool:
                    tool.return_value.returncode = 0
                    tool.return_value.stdout = output
                    path, metadata = save_score_input(upload(data, name), Path(folder))
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(metadata["original_filename"], name)
                self.assertEqual(metadata["pages"], 2 if name.endswith("pdf") else 1)
                self.assertTrue((Path(folder) / "origem.json").is_file())

    def test_selected_pdf_page_preserves_original_and_prepares_single_page(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "Pages: 24\n"
                original, metadata = save_score_input(
                    upload(PDF, "longa.pdf"), job, selected_page=12)
            def fake_run(command, **_kwargs):
                self.assertEqual(command[:5], ["pdfseparate", "-f", "12", "-l", "12"])
                Path(command[-1]).write_bytes(b"%PDF-1.4\npagina de teste")
            with patch("score_omr._run", side_effect=fake_run):
                prepared = prepare_score_source(original, job, metadata)
            self.assertEqual(original.read_bytes(), PDF)
            self.assertNotEqual(prepared, original)
            self.assertEqual(metadata["pages"], 24)
            self.assertEqual(metadata["processed_pages"], 1)
            self.assertEqual(metadata["selected_page"], 12)

    def test_new_image_is_converted_without_changing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "1200 800\n"
                original, metadata = save_score_input(upload(WEBP, "scan.webp"), job)
            def fake_run(command, **_kwargs):
                self.assertIn("-limit", command)
                self.assertEqual(command[0], "convert")
                Path(command[-1].removeprefix("PNG24:")).write_bytes(PNG)
            with patch("score_omr._run", side_effect=fake_run):
                prepared = prepare_score_source(original, job, metadata)
            self.assertEqual(original.read_bytes(), WEBP)
            self.assertEqual(prepared.read_bytes(), PNG)
            self.assertEqual(prepared.suffix, ".png")

    def test_rejects_false_extension_and_too_many_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ScoreInputError, "assinatura"):
                save_score_input(upload(b"not a PDF", "score.pdf"), Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "Pages: 9\n"
                with self.assertRaisesRegex(ScoreInputError, "8 páginas"):
                    save_score_input(upload(PDF, "score.pdf"), Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "Pages: 3\n"
                with self.assertRaisesRegex(ScoreInputError, "entre 1 e 3"):
                    save_score_input(upload(PDF, "score.pdf"), Path(folder), selected_page=4)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ScoreInputError, "apenas para PDF"):
                save_score_input(upload(PNG, "score.png"), Path(folder), selected_page=1)
        with tempfile.TemporaryDirectory() as folder:
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "1200 800\n1200 800\n"
                with self.assertRaisesRegex(ScoreInputError, "vários quadros"):
                    save_score_input(upload(GIF, "animado.gif"), Path(folder))

    def test_requires_audiveris(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("score_omr.available_tools", return_value=(None, sys.executable)):
                with self.assertRaisesRegex(ScoreToolError, "Audiveris"):
                    recognize_score(Path(folder) / "original.pdf", Path(folder))

    def test_recognition_contract_keeps_native_project_and_both_exports(self):
        def fake_run(command, **_kwargs):
            if "-batch" in command:
                self.assertIn("-transcribe", command)
                self.assertTrue(_kwargs["audiveris_tool"])
                fake_audiveris_book(Path(command[command.index("-output") + 1]))
            else:
                output = Path(command[command.index("-o") + 1])
                if output.suffix == ".mid":
                    output.write_bytes(b"MThd1234")
                else:
                    output.write_text(
                        '<score-partwise version="4.0"><part id="P1">'
                        '<measure number="1"><note><rest/></note></measure>'
                        '</part></score-partwise>', encoding="utf-8"
                    )

        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            original = job / "partitura_original.pdf"
            original.write_bytes(PDF)
            with patch("score_omr.available_tools", return_value=(sys.executable, sys.executable)), \
                    patch("score_omr._run", side_effect=fake_run):
                result = recognize_score(original, job)
            self.assertTrue(result["omr_path"].is_file())
            self.assertTrue(result["mxl_path"].is_file())
            self.assertTrue(result["xml_path"].is_file())
            self.assertEqual(result["mid_path"].read_bytes()[:4], b"MThd")

    def test_rejects_empty_musicxml_even_if_tools_report_success(self):
        def fake_run(command, **_kwargs):
            if "-batch" in command:
                fake_audiveris_book(Path(command[command.index("-output") + 1]))
            else:
                output = Path(command[command.index("-o") + 1])
                if output.suffix == ".mid":
                    output.write_bytes(b"MThd1234")
                else:
                    output.write_text('<score-partwise version="4.0"/>', encoding="utf-8")

        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            with patch("score_omr.available_tools", return_value=(sys.executable, sys.executable)), \
                    patch("score_omr._run", side_effect=fake_run):
                with self.assertRaisesRegex(ScoreToolError, "vazio"):
                    recognize_score(job / "partitura_original.pdf", job)

    def test_rejects_corrupt_native_project(self):
        def fake_run(command, **_kwargs):
            fake_audiveris_book(Path(command[command.index("-output") + 1]))
            native = Path(command[command.index("-output") + 1]) / "partitura_original"
            (native / "partitura_original.omr").write_bytes(b"not-a-zip")

        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            with patch("score_omr.available_tools", return_value=(sys.executable, sys.executable)), \
                    patch("score_omr._run", side_effect=fake_run):
                with self.assertRaisesRegex(ScoreToolError, "inválido"):
                    recognize_score(job / "partitura_original.pdf", job)

    def test_route_rejects_missing_and_invalid_input_without_jobs(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as folder, patch("webapp.app.JOBS_DIR", Path(folder)):
            response = client.post("/reconhecer-partitura")
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"Nenhuma partitura", response.data)
            response = client.post(
                "/reconhecer-partitura", data={"score": (io.BytesIO(b"fake"), "score.pdf")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(Path(folder).iterdir()), [])
            response = client.post(
                "/reconhecer-partitura",
                data={"score": (io.BytesIO(PDF), "score.pdf"), "pdf_page": "1-2"},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_route_selected_pdf_page_reaches_omr_as_single_page(self):
        client = app.test_client()
        observed = {}
        def fake_run(command, **_kwargs):
            Path(command[-1]).write_bytes(b"%PDF-1.4\npagina escolhida")
        def fake_recognize(prepared, job_dir):
            observed["source"] = prepared
            observed["original"] = (job_dir / "partitura_original.pdf").read_bytes()
        with tempfile.TemporaryDirectory() as folder, patch("webapp.app.JOBS_DIR", Path(folder)), \
                patch("score_omr.subprocess.run") as tool, \
                patch("score_omr._run", side_effect=fake_run), \
                patch("webapp.app.recognize_score", side_effect=fake_recognize):
            tool.return_value.returncode = 0
            tool.return_value.stdout = "Pages: 12\n"
            response = client.post(
                "/reconhecer-partitura",
                data={"score": (io.BytesIO(PDF), "longa.pdf"), "pdf_page": "9"},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Página 9 de 12".encode(), response.data)
            self.assertEqual(observed["source"].name, "partitura_para_omr.pdf")
            self.assertEqual(observed["original"], PDF)
            job = next(Path(folder).iterdir())
            metadata = json.loads((job / "origem.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["selected_page"], 9)
            self.assertEqual(metadata["processed_pages"], 1)

    def test_route_result_and_downloads_with_mocked_omr(self):
        client = app.test_client()
        def fake_recognize(_original, job_dir):
            (job_dir / "resultado.musicxml").write_text(
                '<score-partwise version="4.0"/>', encoding="utf-8"
            )
            (job_dir / "resultado.mid").write_bytes(b"MThd1234")
            native = job_dir / "audiveris" / "partitura_original"
            native.mkdir(parents=True)
            (native / "partitura_original.mxl").write_bytes(b"MXL-DE-TESTE")
            (native / "partitura_original.omr").write_bytes(b"OMR-DE-TESTE")
            return {"structure_review": {"parts": 1, "measures": 2,
                    "pitched_notes": 3, "rests": 1, "checked_measures": 0,
                    "skipped_measures": 2, "warning_count": 1,
                    "warnings": [{"part": "P1", "measure": "2",
                                  "message": "Compasso de teste para revisão."}],
                    "limited": False}}

        with tempfile.TemporaryDirectory() as folder, patch("webapp.app.JOBS_DIR", Path(folder)), \
                patch("webapp.app.recognize_score", side_effect=fake_recognize):
            # O arquivo mínimo do teste não é PDF válido para pdfinfo; a checagem
            # de páginas é simulada, mas o upload e o job são reais.
            with patch("score_omr.subprocess.run") as tool:
                tool.return_value.returncode = 0
                tool.return_value.stdout = "Pages: 1\n"
                response = client.post(
                    "/reconhecer-partitura",
                    data={"score": (io.BytesIO(PDF), "minha.pdf"),
                          "score_author": "Autora de teste"},
                    content_type="multipart/form-data",
                )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"MusicXML", response.data)
            self.assertIn(f'/download/{next(Path(folder).iterdir()).name}/review'.encode(), response.data)
            self.assertIn("Conferência estrutural inicial".encode(), response.data)
            self.assertIn("Compasso de teste para revisão".encode(), response.data)
            self.assertIn(b"MIDI", response.data)
            self.assertIn(b'/exportar/', response.data)
            self.assertIn(str(Path(folder)).encode(), response.data)
            job_ids = [path.name for path in Path(folder).iterdir()]
            self.assertEqual(len(job_ids), 1)
            job_id = job_ids[0]
            midi = client.get(f"/download/{job_id}/mid")
            xml = client.get(f"/download/{job_id}/musicxml")
            try:
                self.assertEqual(midi.data, b"MThd1234")
                self.assertIn(b"score-partwise", xml.data)
            finally:
                midi.close()
                xml.close()
            self.assertTrue((Path(folder) / job_id / "partitura_original.pdf").is_file())
            mxl = client.get(f"/download/{job_id}/mxl")
            omr = client.get(f"/download/{job_id}/omr")
            try:
                self.assertEqual(mxl.data, b"MXL-DE-TESTE")
                self.assertEqual(omr.data, b"OMR-DE-TESTE")
            finally:
                mxl.close()
                omr.close()
            metadata = json.loads((Path(folder) / job_id / "origem.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["score_author"], "Autora de teste")
            saved_review = json.loads((Path(folder) / job_id / "revisao_estrutura.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_review["warning_count"], 1)
            report_download = client.get(f"/download/{job_id}/review")
            try:
                self.assertEqual(report_download.status_code, 200)
                self.assertEqual(json.loads(report_download.data)["warning_count"], 1)
            finally:
                report_download.close()

    def test_only_one_omr_job_at_a_time(self):
        client = app.test_client()
        self.assertTrue(OMR_SLOT.acquire(blocking=False))
        try:
            response = client.post(
                "/reconhecer-partitura", data={"score": (io.BytesIO(PNG), "score.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"processamento", response.data)
        finally:
            OMR_SLOT.release()


if __name__ == "__main__":
    unittest.main()
