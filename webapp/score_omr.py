"""Entrada local de partituras impressas: PDF/imagem -> OMR -> MusicXML/MIDI.

Audiveris e MuseScore são processos opcionais externos, sem código copiado.
O resultado é um rascunho que exige conferência musical no editor.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path


SCORE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
                    ".webp", ".bmp", ".gif", ".heic", ".heif", ".avif"}
CONVERT_TO_PNG = {".webp", ".bmp", ".gif", ".heic", ".heif", ".avif"}
MAX_SCORE_BYTES = 20 * 1024 * 1024
MAX_SCORE_PAGES = 8
MAX_IMAGE_PIXELS = 16_000_000
MAX_PREPARED_IMAGE_BYTES = 100 * 1024 * 1024
MAX_MUSICXML_BYTES = 32 * 1024 * 1024
AUDIVERIS_LINUX_BIN = Path("/opt/audiveris/bin/Audiveris")
IMAGE_LIMITS = ["-limit", "thread", "1", "-limit", "memory", "256MiB",
                "-limit", "map", "512MiB", "-limit", "disk", "256MiB",
                "-limit", "time", "30"]


class ScoreInputError(ValueError):
    """Entrada não reconhecida, grande demais ou fora do limite local."""


class ScoreToolError(RuntimeError):
    """Ferramenta ausente ou falha de conversão externa."""


def available_tools() -> tuple[str | None, str | None]:
    configured = os.environ.get("MARAVI_AUDIVERIS_BIN")
    if configured:
        # Um caminho configurado incorreto deve aparecer como indisponível,
        # sem executar silenciosamente uma outra instalação do PATH.
        audiveris = configured if _executable(configured) else None
    else:
        audiveris = (shutil.which("Audiveris") or shutil.which("audiveris")
                     or (str(AUDIVERIS_LINUX_BIN)
                         if _executable(AUDIVERIS_LINUX_BIN) else None))
    configured_musescore = os.environ.get("MARAVI_MUSESCORE_BIN")
    if configured_musescore:
        musescore = configured_musescore if _executable(configured_musescore) else None
    else:
        musescore = next((found for name in ("mscore", "musescore", "musescore4",
                                                   "MuseScore4.exe", "mscore4portable")
                          if (found := shutil.which(name))), None)
    return audiveris, musescore


def _executable(path: str | Path) -> bool:
    return Path(path).is_file() and os.access(path, os.X_OK)


def _image_command(operation: str, *, platform_name: str | None = None) -> list[str] | None:
    """Use modern ImageMagick on every OS; avoid Windows' unrelated convert.exe."""
    if operation not in {"identify", "convert"}:
        raise ValueError("Operação ImageMagick não reconhecida")
    if found := shutil.which("magick"):
        return [found, operation]
    if (platform_name or os.name) == "nt":
        return None
    return [operation] if shutil.which(operation) else None


def _run(command: list[str], *, timeout: int, gui_tool: bool = False,
         audiveris_tool: bool = False) -> None:
    """Executa sem shell e mantém a saída do processo fora da memória."""
    import tempfile

    try:
        environment = os.environ.copy()
        if gui_tool and sys.platform.startswith("linux"):
            environment["QT_QPA_PLATFORM"] = "offscreen"
        if audiveris_tool:
            java_options = environment.get("JAVA_TOOL_OPTIONS", "").strip()
            if "-Djava.awt.headless=" not in java_options:
                java_options = f"{java_options} -Djava.awt.headless=true".strip()
            if "-Xmx" not in java_options:
                java_options = f"{java_options} -Xmx1536m".strip()
            environment["JAVA_TOOL_OPTIONS"] = java_options
        with tempfile.TemporaryFile(mode="w+b") as log:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix", env=environment,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
                raise ScoreToolError(f"{Path(command[0]).name} excedeu o tempo de processamento.") from exc
            if returncode:
                log.seek(0, os.SEEK_END)
                log.seek(max(0, log.tell() - 1600))
                detail = log.read().decode("utf-8", errors="replace").strip()
                raise ScoreToolError(
                    f"Falha em {Path(command[0]).name} (código {returncode}). "
                    f"{detail[-1200:]}"
                )
    except OSError as exc:
        raise ScoreToolError(f"Não foi possível executar {Path(command[0]).name}: {exc}") from exc


def save_score_input(upload, job_dir: Path, *, attribution: dict | None = None,
                     selected_page: int | None = None) -> tuple[Path, dict]:
    """Copia no máximo 20 MiB, valida assinatura e número/tamanho de páginas."""
    original_name = upload.filename.replace("\\", "/").split("/")[-1][:200]
    ext = Path(original_name).suffix.lower()
    if ext not in SCORE_EXTENSIONS:
        raise ScoreInputError("Formato não aceito. Use PDF, PNG, JPG/JPEG, TIFF, WebP, BMP, GIF, HEIC/HEIF ou AVIF.")
    if selected_page is not None and ext != ".pdf":
        raise ScoreInputError("A escolha de página vale apenas para PDF.")

    target = job_dir / f"partitura_original{ext}"
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while chunk := upload.stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_SCORE_BYTES:
                raise ScoreInputError("Partitura acima do limite de 20 MB.")
            output.write(chunk)
            digest.update(chunk)
    if size == 0:
        raise ScoreInputError("O arquivo está vazio.")

    with target.open("rb") as source:
        signature = source.read(16)
    brand = signature[8:12] if signature[4:8] == b"ftyp" else b""
    signatures = {
        ".pdf": signature.startswith(b"%PDF-"),
        ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": signature.startswith(b"\xff\xd8\xff"),
        ".jpeg": signature.startswith(b"\xff\xd8\xff"),
        ".tif": signature.startswith((b"II*\x00", b"MM\x00*")),
        ".tiff": signature.startswith((b"II*\x00", b"MM\x00*")),
        ".webp": signature.startswith(b"RIFF") and signature[8:12] == b"WEBP",
        ".bmp": signature.startswith(b"BM"),
        ".gif": signature.startswith((b"GIF87a", b"GIF89a")),
        ".heic": brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1"),
        ".heif": brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1"),
        ".avif": brand == b"avif",
    }
    if not signatures[ext]:
        raise ScoreInputError("A assinatura do arquivo não corresponde ao formato indicado.")

    if ext == ".pdf":
        if not shutil.which("pdfinfo"):
            raise ScoreToolError("pdfinfo não está instalado; não foi possível verificar o PDF.")
        try:
            info = subprocess.run(
                ["pdfinfo", str(target)], stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=15, check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise ScoreInputError("Não foi possível ler as páginas do PDF.") from exc
        match = re.search(r"^Pages:\s*(\d+)\s*$", info.stdout, re.MULTILINE)
        if info.returncode or match is None:
            raise ScoreInputError("PDF inválido, protegido ou sem páginas legíveis.")
        pages = int(match.group(1))
    else:
        image_command = _image_command("identify")
        if not image_command:
            raise ScoreToolError("ImageMagick (magick/identify) não está instalado; não foi possível verificar a imagem.")
        try:
            info = subprocess.run(
                [*image_command, *IMAGE_LIMITS, "-ping", "-format", "%w %h\n", str(target)],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=15, check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise ScoreInputError("Não foi possível ler as dimensões da imagem.") from exc
        try:
            dimensions = [tuple(map(int, line.split())) for line in info.stdout.splitlines()]
        except ValueError as exc:
            raise ScoreInputError("Dimensões de imagem inválidas.") from exc
        if info.returncode or not dimensions or any(len(pair) != 2 for pair in dimensions):
            raise ScoreInputError("Imagem inválida ou não reconhecida.")
        if any(width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS
               for width, height in dimensions):
            raise ScoreInputError("Imagem acima do limite de 16 megapixels por página.")
        pages = len(dimensions)
        if ext in CONVERT_TO_PNG and pages != 1:
            raise ScoreInputError("Esta imagem contém vários quadros. Envie uma imagem estática ou PDF/TIFF multipágina.")
    if selected_page is not None and not 1 <= selected_page <= pages:
        raise ScoreInputError(f"Escolha uma página entre 1 e {pages}.")
    if not 1 <= pages <= MAX_SCORE_PAGES and selected_page is None:
        raise ScoreInputError(f"Esta etapa aceita de 1 a {MAX_SCORE_PAGES} páginas por arquivo.")

    metadata = {"original_filename": original_name, "sha256": digest.hexdigest(),
                "bytes": size, "pages": pages, "source_kind": ext.lstrip("."),
                "selected_page": selected_page, "processed_pages": 1 if selected_page else pages}
    if attribution:
        metadata.update({key: str(attribution.get(key, "")).strip()[:500]
                         for key in ("score_author", "source_reference", "rights_note")})
    (job_dir / "origem.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target, metadata


def prepare_score_source(original: Path, job_dir: Path, metadata: dict) -> Path:
    """Prepara cópia para o OMR, sem modificar o PDF/imagem recebido."""
    ext = original.suffix.lower()
    selected_page = metadata.get("selected_page")
    if selected_page is not None:
        if not shutil.which("pdfseparate"):
            raise ScoreToolError("pdfseparate não está instalado; necessário para extrair a página do PDF.")
        prepared = job_dir / "partitura_para_omr.pdf"
        _run(["pdfseparate", "-f", str(selected_page), "-l", str(selected_page),
              str(original), str(prepared)], timeout=30)
    elif ext in CONVERT_TO_PNG:
        image_command = _image_command("convert")
        if not image_command:
            raise ScoreToolError("ImageMagick (magick/convert) não está instalado; necessário para preparar esta imagem.")
        prepared = job_dir / "partitura_para_omr.png"
        _run([*image_command, *IMAGE_LIMITS, f"{original}[0]", "-auto-orient",
              "-background", "white", "-alpha", "remove", "-alpha", "off",
              "-strip", f"PNG24:{prepared}"], timeout=45)
        if prepared.is_file() and prepared.stat().st_size > MAX_PREPARED_IMAGE_BYTES:
            raise ScoreInputError("A imagem preparada excedeu o limite de 100 MB.")
    else:
        return original
    if not prepared.is_file() or prepared.stat().st_size == 0:
        raise ScoreToolError("Não foi possível preparar a página para o reconhecimento.")
    return prepared


def review_musicxml_structure(root: ET.Element) -> dict:
    """Triagem conservadora da saída OMR; não altera nem aprova a partitura."""
    def local(element: ET.Element) -> str:
        return element.tag.rsplit("}", 1)[-1]

    def children(element: ET.Element, name: str) -> list[ET.Element]:
        return [item for item in element if local(item) == name]

    report = {"parts": 0, "measures": 0, "pitched_notes": 0, "rests": 0,
              "checked_measures": 0, "skipped_measures": 0, "warning_count": 0,
              "warnings": [], "limited": False}
    if local(root) != "score-partwise":
        report["skipped_measures"] = 1
        report["warning_count"] = 1
        report["warnings"].append({"part": "Partitura", "measure": "—",
                                   "message": "Formato MusicXML não coberto pela triagem estrutural."})
        return report

    def warn(part: str, measure: str, message: str) -> None:
        report["warning_count"] += 1
        if len(report["warnings"]) < 25:
            report["warnings"].append({"part": part, "measure": measure,
                                       "message": message})
        else:
            report["limited"] = True

    for part_index, part in enumerate(children(root, "part"), start=1):
        report["parts"] += 1
        part_id = part.get("id", f"Parte {part_index}")
        divisions: int | None = None
        beats: int | None = None
        beat_type: int | None = None
        previous_number: int | None = None
        measures = children(part, "measure")
        for measure_index, measure in enumerate(measures):
            if report["measures"] >= 5000:
                report["limited"] = True
                warn(part_id, measure.get("number", "—"),
                     "Triagem interrompida após 5000 compassos; o restante não foi examinado.")
                return report
            report["measures"] += 1
            number = measure.get("number", str(measure_index + 1))
            if number.isascii() and number.isdigit():
                numeric_number = int(number)
                if previous_number is not None and numeric_number > previous_number + 1:
                    warn(part_id, number, f"Numeração salta de {previous_number} para {numeric_number}.")
                elif previous_number is not None and numeric_number == previous_number:
                    warn(part_id, number, "Número de compasso repetido.")
                previous_number = numeric_number

            duration = 0
            complex_timing = False
            notes_started = False
            for item in measure:
                kind = local(item)
                if kind == "attributes":
                    if notes_started and (children(item, "time") or children(item, "divisions")):
                        complex_timing = True
                    for value in children(item, "divisions"):
                        try:
                            divisions = int(value.text or "")
                            if divisions <= 0:
                                divisions = None
                        except ValueError:
                            divisions = None
                    for time in children(item, "time"):
                        beat_nodes = children(time, "beats")
                        type_nodes = children(time, "beat-type")
                        try:
                            beats = int(beat_nodes[0].text or "") if beat_nodes else None
                            beat_type = int(type_nodes[0].text or "") if type_nodes else None
                            if not beats or not beat_type or beats < 1 or beat_type < 1:
                                beats = beat_type = None
                        except ValueError:
                            beats = beat_type = None
                elif kind in ("backup", "forward"):
                    complex_timing = True
                elif kind == "note":
                    notes_started = True
                    if children(item, "pitch"):
                        report["pitched_notes"] += 1
                    elif children(item, "rest"):
                        report["rests"] += 1
                    if children(item, "chord") or children(item, "grace"):
                        complex_timing = True
                        continue
                    values = children(item, "duration")
                    if not values:
                        complex_timing = True
                        continue
                    try:
                        value = int(values[0].text or "")
                        if value < 0:
                            complex_timing = True
                        else:
                            duration += value
                    except ValueError:
                        complex_timing = True

            # Anacruse, coda parcial, cadenza e múltiplas vozes podem ter
            # métricas válidas diferentes: nesses casos, não inventar erro.
            is_edge = measure_index in (0, len(measures) - 1)
            multiple_rest = any(local(node) == "multiple-rest" for node in measure.iter())
            if (complex_timing or is_edge or multiple_rest or measure.get("implicit") == "yes"
                    or None in (divisions, beats, beat_type)):
                report["skipped_measures"] += 1
                continue
            report["checked_measures"] += 1
            expected = Fraction(beats * 4 * divisions, beat_type)
            if duration != expected:
                warn(part_id, number,
                     f"Duração escrita {Fraction(duration, divisions)} semínimas; "
                     f"compasso {beats}/{beat_type} espera {expected / divisions}.")
    if report["pitched_notes"] == 0:
        warn("Partitura", "—", "Nenhuma nota com altura foi encontrada; confira a leitura OMR.")
    return report


def recognize_score(original: Path, job_dir: Path) -> dict:
    """Gera .omr/.mxl e derivados .musicxml/.mid; nunca edita a entrada."""
    audiveris, musescore = available_tools()
    if not audiveris or not _executable(audiveris):
        raise ScoreToolError("Audiveris não está instalado ou configurado em MARAVI_AUDIVERIS_BIN.")
    if not musescore:
        raise ScoreToolError("MuseScore não está instalado; necessário para MusicXML e MIDI.")

    omr_output = job_dir / "audiveris"
    omr_output.mkdir()
    _run([audiveris, "-batch", "-save", "-transcribe", "-export", "-output", str(omr_output),
          "--", str(original)], timeout=240, audiveris_tool=True)
    exports = sorted(omr_output.rglob("*.mxl"))
    if len(exports) != 1:
        raise ScoreToolError(
            "O Audiveris não gerou uma partitura única. Confira as páginas no aplicativo Audiveris."
        )
    books = sorted(omr_output.rglob("*.omr"))
    if len(books) != 1:
        raise ScoreToolError("O Audiveris não salvou um projeto .omr para revisão posterior.")
    if not zipfile.is_zipfile(exports[0]) or not zipfile.is_zipfile(books[0]):
        raise ScoreToolError("O projeto .omr ou o MusicXML compactado do Audiveris está inválido.")

    xml_path = job_dir / "resultado.musicxml"
    mid_path = job_dir / "resultado.mid"
    _run([musescore, "-s", "-o", str(xml_path), str(exports[0])], timeout=90, gui_tool=True)
    _run([musescore, "-s", "-o", str(mid_path), str(exports[0])], timeout=90, gui_tool=True)
    if not xml_path.is_file() or not mid_path.is_file():
        raise ScoreToolError("A conversão terminou sem os dois arquivos esperados.")
    if xml_path.stat().st_size > MAX_MUSICXML_BYTES:
        raise ScoreToolError("O MusicXML excedeu o limite de 32 MB desta etapa.")
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        raise ScoreToolError("O MusicXML exportado não é XML válido.") from exc
    if root.tag.split("}")[-1] not in ("score-partwise", "score-timewise"):
        raise ScoreToolError("O MusicXML exportado não contém uma partitura reconhecida.")
    # A execução pode terminar sem erro e ainda produzir somente a estrutura
    # vazia de um documento, sem nenhuma pauta/medida a revisar.
    if not any(element.tag.split("}")[-1] == "measure" for element in root.iter()):
        raise ScoreToolError("O MusicXML exportado está vazio: nenhuma medida reconhecida.")
    with mid_path.open("rb") as midi:
        midi_header = midi.read(4)
    if midi_header != b"MThd":
        raise ScoreToolError("O arquivo MIDI exportado não tem cabeçalho válido.")

    return {"mxl_path": exports[0], "omr_path": books[0],
            "xml_path": xml_path, "mid_path": mid_path,
            "structure_review": review_musicxml_structure(root)}
