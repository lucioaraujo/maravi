"""Descarta notas do Basic Pitch que não coincidem com um ataque real.

Autor, 2026-08-31, comparando com a referência do "Le Magicien Baroque"
(flauta solo): a partitura saiu quase toda em semicolcheia e fusa, o
autor escreveu quase toda em colcheia. Medido: o Basic Pitch devolve
~8,7 notas/s, mas `librosa.onset.onset_detect` (independente, robusto em
material monofônico) acha ~6,2 ataques/s. As ~2,5 notas fantasma por
segundo caem ENTRE os ataques reais - quando `beat_grid.
detect_beat_divisions` vê 4-5 ataques numa batida que tem 2-3, ele
escolhe a subdivisão fina que "explica" os fantasmas.

## O que faz

Mantém uma nota do Basic Pitch só se o início dela cai perto de um
ataque REAL (detectado no áudio por fluxo espectral, não pelo modelo).
Uma nota descartada não some do som - a anterior é esticada até onde ela
começava, porque um "início" fantasma quase sempre é o próprio modelo
partindo uma nota real em duas no meio de um vibrato ou de uma
transição.

Só faz sentido em material MONOFÔNICO (uma linha), onde a detecção de
ataque por energia é confiável. Em stem multi-voz (ParMePerdre) os
ataques de vozes diferentes se somam e o filtro apagaria nota real - por
isso é OPT-IN (`--solo` na CLI), não padrão.
"""
from __future__ import annotations


def filter_to_real_onsets(
    melody: list[dict],
    audio_path,
    tolerance: float = 0.045,
) -> dict:
    """Devolve `{melody, kept, dropped, real_onsets}`.

    `tolerance`: janela (segundos) em torno de cada ataque real dentro da
    qual o início de uma nota do Basic Pitch conta como "o mesmo
    ataque". 45ms cobre a imprecisão típica do onset por fluxo espectral
    sem deixar passar fantasma (que costuma estar 80-150ms fora de
    qualquer ataque real).
    """
    import warnings

    import librosa
    import numpy as np

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, backtrack=True, units="frames"
    )
    real_onsets = librosa.frames_to_time(onset_frames, sr=sr).tolist()
    if not real_onsets:
        return {"melody": melody, "kept": len(melody), "dropped": 0, "real_onsets": []}

    onsets_arr = np.asarray(real_onsets)

    kept: list[dict] = []
    dropped = 0
    for note in melody:
        d = float(np.min(np.abs(onsets_arr - note["start"])))
        if d <= tolerance:
            kept.append(dict(note))
        else:
            dropped += 1
            # Estica a nota mantida anterior até onde esta começava - o
            # som não muda, só deixa de haver um "novo ataque" ali.
            if kept and kept[-1]["end"] < note["end"]:
                kept[-1]["end"] = note["end"]

    # Nunca esvazia a melodia - se o filtro derrubou quase tudo, a
    # detecção de ataque provavelmente falhou (áudio atípico) e é melhor
    # devolver o original do que uma linha oca.
    if len(kept) < max(4, len(melody) // 4):
        return {
            "melody": melody,
            "kept": len(melody),
            "dropped": 0,
            "real_onsets": real_onsets,
            "note": "filtro desativado - derrubaria notas demais (detecção de ataque não confiável neste áudio)",
        }

    return {"melody": kept, "kept": len(kept), "dropped": dropped, "real_onsets": real_onsets}
