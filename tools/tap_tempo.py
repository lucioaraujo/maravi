"""Andamento definido pelo próprio músico, batido antes da melodia.

Ideia do autor, registrada em 2026-08-20 e implementada em 2026-08-31:
"tive uma ideia para o bpm, liberar o audio para detectar uma sequência
de batidas feitas pelo músico e o maravi detecta o andamento que será
gravado" - depois precisada: "eu havia sugerido que o usuário batesse o
andamento, definisse previamente antes de gravar a melodia (podendo ser
no mesmo take)".

## Por que isto existe

`librosa.beat.beat_track` (o caminho automático) precisa INFERIR a
pulsação a partir da própria melodia. Numa melodia com poucos ataques
nítidos - voz legato, flauta em notas longas - ele erra, e erra feio:
foi exatamente essa fragilidade que produziu um andamento abaixo de 3,6
BPM e quebrou a escrita do `.mid` (ver `MARAVI_CONCEITO.md` seção 7.9).
Uma sequência de palmas/batidas é o oposto disso: ataques percussivos,
isolados e regulares, o material mais fácil que existe pra detectar.

## O que o "mesmo take" resolve de graça

Bater o pulso DENTRO da mesma gravação dá duas coisas, não uma:

1. **O andamento** - a mediana dos intervalos entre as batidas.
2. **O tempo forte** - a melodia entra na batida seguinte à última,
   então o primeiro tempo forte é conhecido por construção, sem
   precisar do parâmetro `--anacrusis-notes` nem de o autor contar
   notas de levada de ouvido.

E resolve um problema que ele mesmo cria: as batidas estão no áudio e
seriam transcritas como notas. Sabendo onde a contagem termina, dá pra
descartá-las - `melody_start_seconds` abaixo.

## Limite honesto

O andamento daqui é CONSTANTE (a grade sintética de
`beat_grid.synthetic_beat_times`). Uma peça com rubato real fica melhor
servida pelo caminho automático, que segue as batidas detectadas uma a
uma. Este módulo é pra quando a detecção automática falha ou quando o
músico quer fixar o andamento de propósito - não substitui o outro.
"""
from __future__ import annotations

# Faixa plausível, a mesma de `beat_grid.average_bpm()` - fora dela é
# sinal de detecção ruim (batidas de menos, ou ataques da melodia
# contados como batida), não de música genuinamente muito lenta/rápida.
MIN_BPM = 20.0
MAX_BPM = 400.0


def detect_tap_tempo(
    audio_path,
    tap_count: int = 4,
    search_seconds: float = 15.0,
    max_spread: float = 0.35,
) -> dict:
    """Lê as `tap_count` primeiras batidas do áudio e devolve o andamento
    que elas definem.

    `search_seconds`: só procura ataques nesse trecho inicial - a
    contagem é curta por definição, e limitar a janela evita que a
    melodia inteira entre na conta.
    `max_spread`: dispersão máxima tolerada entre os intervalos
    (desvio relativo à mediana). Acima disso as "batidas" não são
    regulares o bastante pra serem uma contagem - provavelmente já é a
    melodia, e é melhor falhar com mensagem clara do que devolver um
    andamento inventado.

    Devolve `{bpm, tap_times, interval, spread, melody_start_seconds}`.
    Levanta `ValueError` com mensagem legível em qualquer caso duvidoso -
    a mesma disciplina de `beat_grid.average_bpm()`, adotada depois do
    bug de andamento implausível que quebrava a escrita do MIDI sem
    mensagem nenhuma.
    """
    import warnings

    import librosa
    import numpy as np

    if tap_count < 2:
        raise ValueError("A contagem precisa de pelo menos 2 batidas pra definir um intervalo.")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y, sr = librosa.load(str(audio_path), sr=None, mono=True, duration=search_seconds)

    if y.size == 0:
        raise ValueError("Áudio vazio - não há batidas pra ler.")

    # Separação harmônico/percussivo antes de qualquer contagem. Sem
    # ela é IMPOSSÍVEL saber onde a contagem termina quando a melodia
    # entra no mesmo andamento: os ataques ficam igualmente espaçados,
    # e contar "as N primeiras" pega batida de menos e nota de mais
    # (erro real observado no primeiro teste desta implementação - a
    # palma do instante 0 não foi detectada, então a 4ª "batida" era na
    # verdade a 1ª nota da melodia, e o corte comia essa nota).
    # Palma/batida na mesa é percussiva e sem altura definida; voz,
    # flauta e afins são harmônicas - `hpss` separa exatamente isso.
    y_harmonic, y_percussive = librosa.effects.hpss(y)

    def ataques(sinal):
        frames = librosa.onset.onset_detect(y=sinal, sr=sr, backtrack=True, units="frames")
        return [float(t) for t in librosa.frames_to_time(frames, sr=sr)]

    # `backtrack=True` puxa cada marca pro início real do transiente,
    # não pro pico de energia - importante aqui, porque é a distância
    # entre ataques que vira andamento.
    percussivos = ataques(y_percussive)
    harmonicos = ataques(y_harmonic)

    # A melodia começa no primeiro ataque HARMÔNICO; a contagem é o que
    # vem de percussivo antes disso. Assim o número de batidas
    # realmente detectadas não precisa bater com `tap_count` - ele passa
    # a ser um limite superior/conferência, não uma contagem cega.
    primeiro_harmonico = harmonicos[0] if harmonicos else None
    if primeiro_harmonico is not None:
        taps = [t for t in percussivos if t < primeiro_harmonico]
    else:
        taps = list(percussivos)
    taps = taps[:tap_count]

    if len(taps) < 2:
        raise ValueError(
            f"Encontrei só {len(taps)} batida(s) de contagem antes da melodia "
            f"(nos primeiros {search_seconds:.0f}s). São necessárias pelo menos 2 pra medir "
            "um intervalo. Bata o pulso mais forte/destacado antes de tocar."
        )

    intervals = np.diff(taps)
    interval = float(np.median(intervals))

    if interval <= 0:
        raise ValueError("As batidas detectadas ficaram no mesmo instante - não dá pra medir andamento.")

    spread = float(np.max(np.abs(intervals - interval)) / interval)
    if spread > max_spread:
        raise ValueError(
            f"As batidas não ficaram regulares o bastante (variação de {spread * 100:.0f}% "
            f"entre elas, limite {max_spread * 100:.0f}%). Provavelmente algum ataque da melodia "
            "entrou na contagem, ou a contagem saiu irregular - tente de novo, ou informe o BPM direto."
        )

    bpm = 60.0 / interval
    if not (MIN_BPM <= bpm <= MAX_BPM):
        raise ValueError(
            f"O andamento das batidas deu {bpm:.1f} BPM, fora da faixa musical plausível "
            f"({MIN_BPM:.0f}-{MAX_BPM:.0f}). Verifique a contagem ou informe o BPM manualmente."
        )

    # Ponto de corte: o primeiro ataque harmônico é a primeira nota da
    # melodia, então o corte fica um pouco ANTES dele (nunca em cima) -
    # 15% do intervalo de batida é folga suficiente pro transiente sem
    # deixar nenhuma palma passar. Sem ataque harmônico nenhum (áudio só
    # de percussão, ou melodia que o `hpss` não separou), cai no
    # comportamento antigo: a batida seguinte à última da contagem.
    if primeiro_harmonico is not None:
        melody_start = primeiro_harmonico - interval * 0.15
        # Nunca antes da última batida da contagem - senão a própria
        # palma final voltaria pra dentro da melodia.
        melody_start = max(melody_start, taps[-1] + interval * 0.25)
    else:
        melody_start = taps[-1] + interval * 0.75

    return {
        "bpm": bpm,
        "tap_times": taps,
        "interval": interval,
        "spread": spread,
        "melody_start_seconds": max(0.0, melody_start),
        "first_melody_onset": primeiro_harmonico,
        "tap_count_detected": len(taps),
    }


def trim_melody_before(melody: list[dict], start_seconds: float) -> list[dict]:
    """Descarta o que foi detectado durante a contagem e reancora o
    tempo em zero. Sem isso as próprias palmas viram notas na partitura.

    Uma nota que COMEÇA antes do corte mas atravessa é mantida e apenas
    aparada no ponto de corte - é o caso de uma primeira nota tocada um
    pouco adiantada, que deve entrar na partitura, não sumir."""
    trimmed: list[dict] = []
    for note in melody:
        if note["end"] <= start_seconds:
            continue
        novo = dict(note)
        novo["start"] = max(0.0, note["start"] - start_seconds)
        novo["end"] = note["end"] - start_seconds
        if novo["end"] > novo["start"]:
            trimmed.append(novo)
    return trimmed
