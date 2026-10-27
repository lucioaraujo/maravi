"""Bounded end-to-end smoke test with synthetic, generated audio.

Run only as a release gate: ``python -B tools/smoke_local_release.py``.
It does not test musical accuracy or launch a public server.
"""

from __future__ import annotations

from io import BytesIO
import importlib
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch
import wave
from xml.etree import ElementTree


def synthetic_voice() -> bytes:
    rate = 16000
    samples = bytearray()
    for frequency in (220.0, 261.63, 329.63):
        for i in range(rate):
            fade = min(1.0, i / 240, (rate - i - 1) / 240)
            value = int(9000 * fade * math.sin(2 * math.pi * frequency * i / rate))
            samples.extend(struct.pack("<h", value))
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples)
    return output.getvalue()


def verify_result(client, jobs: Path, audio: bytes, filename: str, *, microphone: bool) -> int:
    response = client.post(
        "/transcrever",
        data={
            "audio": (BytesIO(audio), filename),
            "source": "mic" if microphone else "upload",
            "bpm": "90", "key": "C", "time_signature": "4/4",
            "score_instrument": "voice", "source_isolated": "on",
        },
    )
    if response.status_code != 200:
        raise RuntimeError(f"Transcrição falhou ({response.status_code}): {response.get_data(as_text=True)[:400]}")
    match = re.search(rb"/download/([0-9a-f]{12})/musicxml", response.data)
    if match is None:
        raise RuntimeError("Resultado não contém o link de MusicXML")
    job_id = match.group(1).decode("ascii")
    job = jobs / job_id
    root = ElementTree.parse(job / "resultado.musicxml").getroot()
    pitched = [note for note in root.findall(".//note") if note.find("pitch") is not None]
    midi = job / "resultado.mid"
    if not pitched or not midi.is_file() or midi.stat().st_size < 20:
        raise RuntimeError("MusicXML/MIDI vazio ou ausente")
    if root.findtext(".//score-part/part-name") != "Voz":
        raise RuntimeError("Resultado não foi rotulado como Voz")
    if microphone and not (job / "entrada_convertida.wav").is_file():
        raise RuntimeError("Gravação de microfone não foi convertida para WAV")
    if client.get(f"/download/{job_id}/musicxml").status_code != 200:
        raise RuntimeError("Download local de MusicXML falhou")
    return len(pitched)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    webapp = importlib.import_module("webapp.app")
    with tempfile.TemporaryDirectory(prefix="maravi-release-smoke-") as folder:
        jobs = Path(folder) / "jobs"
        jobs.mkdir()
        with patch.object(webapp, "JOBS_DIR", jobs):
            client = webapp.app.test_client()
            wav = synthetic_voice()
            count = verify_result(client, jobs, wav, "sintese.wav", microphone=False)
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise RuntimeError("ffmpeg ausente: não é possível validar o microfone")
            encoded = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
                 "-c:a", "libopus", "-f", "ogg", "pipe:1"],
                input=wav, capture_output=True, timeout=15, check=True,
            )
            mic_count = verify_result(client, jobs, encoded.stdout, "gravacao_mic.ogg", microphone=True)
            print(f"OK: WAV ({count} segmentos) e microfone OGG ({mic_count} segmentos) → MusicXML, MIDI e download local")


if __name__ == "__main__":
    main()
