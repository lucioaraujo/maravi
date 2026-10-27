#!/usr/bin/env python3
"""Teste local opt-in: PDF autoral -> Audiveris -> Maravi -> MusicXML/MIDI.

Requer MARAVI_AUDIVERIS_BIN e MuseScore instalados. Não integra a suíte
rápida, não acessa partituras de terceiros e remove seus próprios temporários.
Executar com timeout externo, por exemplo `timeout 120 ...`.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webapp.app import app  # noqa: E402
from webapp.score_omr import available_tools  # noqa: E402
from score_diff import compare_scores, read_score  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("pdf", "png", "jpg", "tif", "webp"), default="pdf",
                        help="tipo de entrada submetida ao Maravi")
    parser.add_argument("--pages", type=int, choices=(1, 2), default=1,
                        help="uma ou duas páginas; duas páginas exigem PDF")
    parser.add_argument("--selected-page", type=int, choices=(1, 2),
                        help="reconhecer somente esta página do PDF")
    args = parser.parse_args()
    if args.pages == 2 and args.format != "pdf":
        parser.error("duas páginas requerem --format pdf")
    if args.selected_page and (args.format != "pdf" or args.selected_page > args.pages):
        parser.error("--selected-page deve apontar para uma página existente do PDF")
    audiveris, musescore = available_tools()
    if not audiveris or not musescore:
        raise RuntimeError("Configure MARAVI_AUDIVERIS_BIN e instale o MuseScore.")

    fixture = ROOT / "tests/fixtures/omr_smoke.musicxml"
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="maravi-omr-smoke-") as folder:
        work = Path(folder)
        for name, key in (("config", "XDG_CONFIG_HOME"), ("cache", "XDG_CACHE_HOME"),
                          ("data", "XDG_DATA_HOME")):
            path = work / name
            path.mkdir()
            os.environ[key] = str(path)
        score_source = fixture
        if args.pages == 2:
            tree = ET.parse(fixture)
            system_break = tree.find(".//measure[@number='5']/print")
            if system_break is None:
                raise RuntimeError("O modelo não contém quebra antes do quinto compasso.")
            system_break.attrib.clear()
            system_break.set("new-page", "yes")
            score_source = work / "duas_paginas.musicxml"
            tree.write(score_source, encoding="utf-8", xml_declaration=True)

        pdf = work / "partitura_teste.pdf"
        subprocess.run(
            [musescore, "-s", "-o", str(pdf), str(score_source)],
            check=True, timeout=30, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        if args.pages == 2:
            info = subprocess.run(["pdfinfo", str(pdf)], check=True, timeout=15,
                                  capture_output=True, text=True)
            if not re.search(r"^Pages:\s*2\s*$", info.stdout, re.MULTILINE):
                raise RuntimeError("MuseScore não produziu o PDF de duas páginas.")
        score_input = pdf
        if args.format != "pdf":
            prefix = work / "partitura_teste"
            raster_format = "png" if args.format == "webp" else args.format
            subprocess.run(
                ["pdftoppm", "-f", "1", "-l", "1", "-r", "300", "-gray",
                 "-singlefile", "-" + {"png": "png", "jpg": "jpeg", "tif": "tiff"}[raster_format],
                 str(pdf), str(prefix)],
                check=True, timeout=30, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            score_input = prefix.with_suffix(f".{raster_format}")
            if args.format == "webp":
                converted = prefix.with_suffix(".webp")
                subprocess.run(
                    ["convert", "-limit", "thread", "1", str(score_input),
                     "-define", "webp:lossless=true", str(converted)],
                    check=True, timeout=30, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )
                score_input = converted
            if not score_input.is_file():
                raise RuntimeError(f"A imagem {score_input.name} não foi criada.")
        jobs = work / "jobs"
        jobs.mkdir()
        with patch("webapp.app.JOBS_DIR", jobs), score_input.open("rb") as source:
            response = app.test_client().post(
                "/reconhecer-partitura",
                data={"score": (source, score_input.name),
                      "pdf_page": str(args.selected_page) if args.selected_page else "",
                      "score_author": "Lúcio de Araújo",
                      "source_reference": "Maravi OMR Smoke, partitura autoral"},
                content_type="multipart/form-data",
            )
        if response.status_code != 200:
            raise RuntimeError(f"Upload OMR falhou: HTTP {response.status_code}; "
                               f"{response.get_data(as_text=True)[-900:]}")

        job_dirs = list(jobs.iterdir())
        if len(job_dirs) != 1:
            raise RuntimeError("O fluxo não criou um único job.")
        job = job_dirs[0]
        for filename in (f"partitura_original.{args.format}", "origem.json",
                         "resultado.musicxml", "resultado.mid", "revisao_estrutura.json"):
            if not (job / filename).is_file():
                raise RuntimeError(f"Faltou o arquivo {filename}.")
        if len(list((job / "audiveris").glob("*.omr"))) != 1:
            raise RuntimeError("Faltou o projeto .omr revisável.")
        if len(list((job / "audiveris").glob("*.mxl"))) != 1:
            raise RuntimeError("Faltou o MusicXML compactado.")

        before = read_score(fixture)
        after = read_score(job / "resultado.musicxml")
        if args.selected_page:
            expected = list(before.values())[(args.selected_page - 1) * 4:args.selected_page * 4]
            actual = list(after.values())
            changes = [index + 1 for index, (a, b) in enumerate(zip(expected, actual))
                       if a.alturas != b.alturas or a.ritmo != b.ritmo]
            if len(expected) != len(actual):
                changes.append("contagem de compassos")
        else:
            changes = compare_scores(before, after)
        print(f"{args.format.upper()} ({args.pages} página(s), seleção {args.selected_page or 'todas'}): HTTP 200; "
              f".omr/.mxl/MusicXML/MIDI presentes; "
              f"{len(expected) if args.selected_page else len(before)} compassos esperados, "
              f"{len(after)} no resultado; "
              f"{len(changes)} compassos com diferenças musicais")
        print(f"tempo {time.monotonic() - start:.1f}s; "
              f"pico RSS de processo filho {resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024:.0f} MiB")
        if changes:
            raise RuntimeError(f"Diferenças musicais no teste autoral: {changes}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"Teste OMR real falhou: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
