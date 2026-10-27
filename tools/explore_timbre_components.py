#!/usr/bin/env python3
"""Experimento local e curto: componentes espectrais para escuta comparativa.

Não identifica nem isola automaticamente uma flauta. HPSS separa energia
harmônica da percussiva; NMF divide a energia harmônica em padrões espectrais
que ainda podem conter mais de um instrumento. Nenhum stem gerado aqui deve
ser transcrito como flauta sem audição e confirmação humana.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from sklearn.decomposition import NMF
from threadpoolctl import threadpool_limits

SAMPLE_RATE = 16000
N_FFT = 1024
HOP_LENGTH = 256
MAX_SECONDS = 12.0


def component_masks(templates: np.ndarray, activations: np.ndarray) -> np.ndarray:
    """Máscaras não negativas cuja soma por bin é aproximadamente 1."""
    contributions = templates.T[:, :, None] * activations[:, None, :]
    total = contributions.sum(axis=0, keepdims=True)
    return contributions / np.maximum(total, np.finfo(np.float32).eps)


def decode_excerpt(path: Path, start: float, duration: float) -> np.ndarray:
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-i", str(path),
        "-t", str(duration), "-vn", "-sn", "-dn", "-ac", "1", "-ar",
        str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, timeout=30, check=True)
    audio = np.frombuffer(result.stdout, dtype="<f4")[: int(duration * SAMPLE_RATE)].copy()
    if audio.size < SAMPLE_RATE:
        raise ValueError("O trecho decodificado precisa conter ao menos 1 segundo de áudio.")
    return audio


def explore(audio: np.ndarray, components: int) -> tuple[np.ndarray, list[np.ndarray], list[dict]]:
    if audio.ndim != 1 or audio.size > int(MAX_SECONDS * SAMPLE_RATE):
        raise ValueError("O áudio do experimento deve ser mono e ter até 12 segundos.")
    if not 2 <= components <= 8:
        raise ValueError("Use de 2 a 8 componentes.")

    spectrum = librosa.stft(audio, n_fft=N_FFT, hop_length=HOP_LENGTH)
    harmonic, _percussive = librosa.decompose.hpss(spectrum)
    magnitude = np.abs(harmonic).astype(np.float32)
    if np.max(magnitude) <= 1e-7:
        raise ValueError("Não foi encontrada energia harmônica suficiente no trecho.")

    model = NMF(n_components=components, init="nndsvda", solver="mu",
                max_iter=100, tol=0.005, random_state=0)
    # sklearn espera observações no primeiro eixo: frames x frequências.
    with threadpool_limits(limits=1):
        activations = model.fit_transform(magnitude.T).T.astype(np.float32)
    templates = model.components_.T.astype(np.float32)
    masks = component_masks(templates, activations)
    harmonic_audio = librosa.istft(harmonic, hop_length=HOP_LENGTH, length=len(audio))
    outputs = []
    stats = []
    freqs = librosa.fft_frequencies(sr=SAMPLE_RATE, n_fft=N_FFT)
    for index, mask in enumerate(masks):
        separated = librosa.istft(harmonic * mask, hop_length=HOP_LENGTH,
                                  length=len(audio)).astype(np.float32)
        spectrum_weight = templates[:, index]
        centroid = float(np.dot(freqs, spectrum_weight) / max(spectrum_weight.sum(), 1e-12))
        stats.append({
            "component": index + 1,
            "rms": float(np.sqrt(np.mean(separated * separated))),
            "spectral_centroid_hz": round(centroid),
        })
        outputs.append(separated)
    return harmonic_audio, outputs, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("output_dir", type=Path, help="Nova pasta local; não sobrescreve arquivos")
    parser.add_argument("--start", type=float, default=0.0, help="Início do trecho em segundos")
    parser.add_argument("--duration", type=float, default=8.0, help="Entre 1 e 12 segundos")
    parser.add_argument("--components", type=int, default=6, help="Entre 2 e 8 padrões")
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error("O arquivo de áudio não existe.")
    if not 0 <= args.start <= 36000 or not 1 <= args.duration <= MAX_SECONDS:
        parser.error("Use início >= 0 e duração entre 1 e 12 segundos.")
    if not 2 <= args.components <= 8:
        parser.error("Use de 2 a 8 componentes.")
    if args.output_dir.exists():
        parser.error("A pasta de saída já existe; escolha uma pasta nova.")

    audio = decode_excerpt(args.audio, args.start, args.duration)
    harmonic, components, stats = explore(audio, args.components)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sf.write(args.output_dir / "00_mistura.wav", audio, SAMPLE_RATE, subtype="PCM_16")
    sf.write(args.output_dir / "01_harmonico.wav", harmonic, SAMPLE_RATE, subtype="PCM_16")
    for index, component in enumerate(components, 1):
        sf.write(args.output_dir / f"componente_{index:02d}.wav", component,
                 SAMPLE_RATE, subtype="PCM_16")
    manifest = {
        "source": str(args.audio), "start_seconds": args.start,
        "duration_seconds": len(audio) / SAMPLE_RATE, "sample_rate": SAMPLE_RATE,
        "components": stats, "method": "HPSS + NMF em magnitude harmônica",
        "warning": "Componentes espectrais sem identificação instrumental; não são stems de flauta.",
    }
    (args.output_dir / "manifesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(args.output_dir)
    for item in stats:
        print(f"{item['component']:02d}: RMS={item['rms']:.5f}, centroide={item['spectral_centroid_hz']} Hz")


if __name__ == "__main__":
    main()
