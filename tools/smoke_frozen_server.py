"""Smoke test of a frozen Maravi binary on the local loopback interface.

Run with ``python -B tools/smoke_frozen_server.py /path/to/Maravi``.
The child server is always stopped; this does not publish a service.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from smoke_local_release import synthetic_voice


def free_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def post_synthetic_preview(port: int, audio: bytes) -> None:
    boundary = "maravi-preview-smoke-boundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"sintese.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n".encode() + audio
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = Request(
        f"http://127.0.0.1:{port}/analisar-audio", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=75) as response:
        data = json.load(response)
        if response.status != 200 or data.get("channels") != 1 or data.get("sample_seconds", 0) < 2.9:
            raise RuntimeError(f"Pré-análise congelada inválida: {data}")


def post_synthetic_audio(port: int, audio: bytes, filename: str, *, microphone: bool) -> None:
    boundary = "maravi-release-smoke-boundary"
    fields = {"bpm": "90", "key": "C", "time_signature": "4/4",
              "score_instrument": "voice", "source_isolated": "on"}
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{filename}\"\r\n"
         f"Content-Type: {'audio/ogg' if microphone else 'audio/wav'}\r\n\r\n").encode()
        + audio + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    request = Request(
        f"http://127.0.0.1:{port}/transcrever", data=b"".join(parts), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=90) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"Transcrição empacotada retornou HTTP {response.status}")
    match = re.search(rb"/download/([0-9a-f]{12})/musicxml", body)
    if match is None:
        raise RuntimeError(f"Resultado empacotado sem MusicXML: {body[-400:]!r}")
    job_id = match.group(1).decode("ascii")
    with urlopen(f"http://127.0.0.1:{port}/download/{job_id}/musicxml", timeout=5) as response:
        if response.status != 200 or b"<score-partwise" not in response.read():
            raise RuntimeError("Download empacotado de MusicXML falhou")
    with urlopen(f"http://127.0.0.1:{port}/download/{job_id}/mid", timeout=5) as response:
        if response.status != 200 or not response.read().startswith(b"MThd"):
            raise RuntimeError("Download empacotado de MIDI falhou")


def post_synthetic_omr(port: int, work: Path, environment: dict[str, str]) -> None:
    musescore = environment.get("MARAVI_MUSESCORE_BIN") or shutil.which("mscore")
    audiveris = environment.get("MARAVI_AUDIVERIS_BIN")
    if not musescore or not audiveris:
        raise RuntimeError("OMR congelado requer MARAVI_AUDIVERIS_BIN e MuseScore")
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/omr_smoke.musicxml"
    pdf = work / "partitura_teste.pdf"
    subprocess.run(
        [musescore, "-s", "-o", str(pdf), str(fixture)],
        check=True, timeout=30, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        env={**environment, "QT_QPA_PLATFORM": "offscreen"},
    )
    boundary = "maravi-omr-smoke-boundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"score\"; filename=\"partitura_teste.pdf\"\r\n"
        "Content-Type: application/pdf\r\n\r\n".encode() + pdf.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = Request(
        f"http://127.0.0.1:{port}/reconhecer-partitura", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=100) as response:
        html = response.read()
        if response.status != 200:
            raise RuntimeError(f"OMR congelado retornou HTTP {response.status}")
    match = re.search(rb"/download/([0-9a-f]{12})/musicxml", html)
    if match is None:
        raise RuntimeError(f"Resultado OMR sem download: {html[-400:]!r}")
    job_id = match.group(1).decode("ascii")
    for kind in ("musicxml", "mid", "mxl", "omr"):
        with urlopen(f"http://127.0.0.1:{port}/download/{job_id}/{kind}", timeout=10) as response:
            content = response.read()
            if response.status != 200 or not content:
                raise RuntimeError(f"Download OMR {kind} falhou")
            if kind == "musicxml":
                root = ElementTree.fromstring(content)
                if len(root.findall(".//measure")) != 8:
                    raise RuntimeError("OMR congelado não devolveu oito compassos")
            elif kind == "mid" and not content.startswith(b"MThd"):
                raise RuntimeError("MIDI OMR inválido")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--with-omr", action="store_true", help="testa PDF com Audiveris e MuseScore externos")
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    port = free_local_port()
    temporary = tempfile.TemporaryDirectory(prefix="maravi-frozen-smoke-")
    work = Path(temporary.name)
    environment = {**os.environ, "MARAVI_PORT": str(port), "TMPDIR": temporary.name}
    for key, folder in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                        ("XDG_DATA_HOME", "data")):
        path = work / folder
        path.mkdir()
        environment[key] = str(path)
    child = subprocess.Popen(
        [str(executable)],
        cwd=temporary.name,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for path, marker in (
            ("/", b"Transcrever uma melodia"),
            ("/partitura", b"partitura"),
            ("/ajuda", b"Como usar"),
            ("/static/style.css", b"score-workspace"),
            ("/static/app.js", b"mic-btn"),
        ):
            deadline = time.monotonic() + 12
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f"Maravi encerrou antes de servir {path}: {child.stderr.read()[-1200:]}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                        body = response.read()
                        if response.status != 200 or marker not in body:
                            raise RuntimeError(f"Resposta inválida em {path}: HTTP {response.status}")
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Maravi não serviu {path} em 12 s")
                    time.sleep(0.2)
        wav = synthetic_voice()
        post_synthetic_preview(port, wav)
        post_synthetic_audio(port, wav, "sintese.wav", microphone=False)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg ausente: microfone OGG não validado")
        encoded = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
             "-c:a", "libopus", "-f", "ogg", "pipe:1"],
            input=wav, capture_output=True, timeout=15, check=True,
        )
        post_synthetic_audio(port, encoded.stdout, "gravacao_mic.ogg", microphone=True)
        if args.with_omr:
            post_synthetic_omr(port, work, environment)
        print("OK: executável congelado serviu interface, pré-análise, WAV e microfone OGG"
              + (", PDF/OMR" if args.with_omr else "")
              + " → MusicXML/MIDI em 127.0.0.1")
    finally:
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=5)
        temporary.cleanup()


if __name__ == "__main__":
    main()
