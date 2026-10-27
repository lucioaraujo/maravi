#!/usr/bin/env python3
"""Prévia curta do áudio antes da partitura; não identifica instrumentos.

Uso interno do webapp, em subprocesso com timeout. Só os primeiros 20 s são
decodificados a 11,025 kHz; nenhuma nota ou partitura é escrita aqui.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import warnings

from key_detection import detect_key_from_weights

MAX_SECONDS = 20
SAMPLE_RATE = 11025


def analyze(path: Path, channel: str = "mix") -> dict:
    if channel not in {"mix", "left", "right"}:
        raise ValueError("Canal inválido.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels,duration:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=10,
    )
    if probe.returncode != 0:
        raise ValueError("Não foi possível ler o áudio.")
    try:
        metadata = json.loads(probe.stdout)
        stream = metadata["streams"][0]
        channels = int(stream["channels"])
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("O áudio não informa duração e canais verificáveis.") from exc
    duration = None
    for raw in (stream.get("duration"), metadata.get("format", {}).get("duration")):
        try:
            candidate = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            duration = candidate
            break
    if channels < 1 or duration is None:
        raise ValueError("Duração ou canais inválidos.")
    if channel != "mix" and (channels != 2 or duration > 180):
        raise ValueError("A escolha esquerda/direita exige estéreo de até 3 minutos.")

    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
               "-map", "0:a:0", "-t", str(MAX_SECONDS)]
    if channel != "mix":
        command += ["-af", f"pan=mono|c0=c{0 if channel == 'left' else 1}"]
    command += ["-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, timeout=30)
    if decoded.returncode != 0:
        raise ValueError("Falha ao decodificar o trecho para análise prévia.")

    import numpy as np

    audio = np.frombuffer(decoded.stdout, dtype="<f4")
    sample_seconds = len(audio) / SAMPLE_RATE
    result = {
        "duration_seconds": round(duration, 1),
        "channels": channels,
        "sample_seconds": round(sample_seconds, 1),
        "selected_channel": channel,
        "bpm": None,
        "tempo_regularity": None,
        "key_name": None,
        "key_runner_up": None,
        "key_ambiguous": True,
        "instrument": None,
        "meter": None,
    }
    if sample_seconds < 2 or float(np.sqrt(np.mean(audio * audio))) < 0.0001:
        return result

    import librosa

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tempo, beat_frames = librosa.beat.beat_track(
            y=audio, sr=SAMPLE_RATE, hop_length=256,
        )
        if len(beat_frames) >= 4:
            candidate = float(np.asarray(tempo).reshape(-1)[0])
            if math.isfinite(candidate) and 30 <= candidate <= 240:
                result["bpm"] = round(candidate, 1)
                beat_times = librosa.frames_to_time(
                    beat_frames, sr=SAMPLE_RATE, hop_length=256,
                )
                intervals = np.diff(beat_times)
                result["tempo_regularity"] = round(
                    float(np.std(intervals) / np.mean(intervals)), 2,
                )
        chroma = librosa.feature.chroma_stft(
            y=audio, sr=SAMPLE_RATE, n_fft=2048, hop_length=512,
        )
    key = detect_key_from_weights(chroma.mean(axis=1).tolist())
    if key is not None:
        result["key_name"] = key["name"]
        result["key_runner_up"] = key["runner_up"]
        result["key_ambiguous"] = key["confidence"] < 0.55 or key["margin"] < 0.1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--channel", choices=("mix", "left", "right"), default="mix")
    args = parser.parse_args()
    print(json.dumps(analyze(args.audio, args.channel), ensure_ascii=False))


if __name__ == "__main__":
    main()
