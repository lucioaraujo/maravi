"""Onde cai o tempo forte - a fase do compasso dentro da grade de batidas.

Autor, 2026-08-31: "vejo que o importante na maioria das melodias é
definir onde é o tempo forte (que normalmente é o primeiro tempo do
compasso), claro que há exceções, mas identificar isso facilita a
escrita musical."

## O problema, e por que ele sobrevive à grade de batidas

`librosa.beat.beat_track` (e a contagem batida pelo músico) dá as
BATIDAS, não o COMPASSO. Saber que há uma batida a cada 0,57s não diz
qual delas é o "um". Em 2/4, errar a fase por uma batida desloca todas
as barras de compasso pela metade do compasso - a partitura fica
legível, mas musicalmente errada: síncopes viram tempos fortes, e
qualquer leitor tropeça.

Até aqui isso era resolvido só à mão: `--anacrusis-notes N`, o autor
contando de ouvido quantas notas formam a levada antes do primeiro
tempo forte ("desculpe erro meu são 3 notas no anacruse, a quarta nota
é a primeira do compasso"). Funciona, mas exige ouvido treinado e uma
tentativa por arquivo.

Duas situações ficam resolvidas sem isto: quando o músico bate a
contagem no mesmo take (`tools/tap_tempo.py` - o tempo forte é a batida
seguinte à contagem, por construção) e quando o autor informa a
anacruse. Este módulo cobre o resto: áudio já gravado, sem contagem e
sem informação do autor.

## Método (DSP clássica, sem modelo treinado)

Testa as `beats_per_measure` fases possíveis e pontua cada uma por três
evidências que a música dá de graça, todas já disponíveis no pipeline:

1. **Ataque na batida.** Tempo forte tende a ter nota começando nele.
2. **Nota longa.** Valores longos caem preferencialmente no tempo forte
   (a mesma intuição de "nota estrutural" que orienta a simplificação
   estilo Real Book, seção 7 do conceito).
3. **Nota destacada.** Amplitude maior no ataque - acento real.

A fase vencedora é a que melhor explica as três ao mesmo tempo. Não é
infalível: uma melodia sistematicamente sincopada (e choro tem muita
síncope) pode enganar qualquer heurística de acento, e por isso o
resultado devolve uma MARGEM sobre o segundo colocado - margem pequena
é sinal honesto de "isto aqui é ambíguo, confira", não de certeza.
Continua sempre sobreposto por `--anacrusis-notes`, que é informação do
autor e vence estimativa, a mesma regra de `--bpm` e `--key`.
"""
from __future__ import annotations

import bisect


def _beat_index_at(t: float, beat_times: list[float]) -> int:
    """Índice da batida que contém o instante `t`."""
    return max(0, min(bisect.bisect_right(beat_times, t) - 1, len(beat_times) - 1))


def detect_downbeat_phase(
    melody: list[dict],
    beat_times: list[float],
    beats_per_measure: int,
    tolerance: float = 0.25,
) -> dict | None:
    """Descobre qual fase da grade de batidas é o tempo forte.

    `tolerance`: quão perto do início da batida uma nota precisa começar
    pra contar como "em cima" dela, em fração da duração da batida.

    Devolve `{phase, downbeat_time, scores, margin, anacrusis_notes}` ou
    `None` se não houver material pra decidir. `phase` é 0..n-1 (qual
    índice de batida é o "um"); `downbeat_time` é o instante real da
    primeira batida forte; `anacrusis_notes` é quantas notas da melodia
    caem antes dela - o mesmo número que `--anacrusis-notes` esperaria,
    pra poder comparar com o que o autor teria contado de ouvido.
    """
    if beats_per_measure < 2 or len(beat_times) < 2 or not melody:
        return None

    # Evidência acumulada por fase.
    ataques = [0.0] * beats_per_measure
    duracoes = [0.0] * beats_per_measure
    acentos = [0.0] * beats_per_measure

    for note in melody:
        idx = _beat_index_at(note["start"], beat_times)
        inicio_batida = beat_times[idx]
        fim_batida = beat_times[idx + 1] if idx + 1 < len(beat_times) else inicio_batida + (beat_times[-1] - beat_times[-2])
        duracao_batida = fim_batida - inicio_batida
        if duracao_batida <= 0:
            continue
        # Só notas que começam PERTO do início da batida são evidência de
        # tempo forte - uma nota no meio da batida não diz nada sobre a
        # fase do compasso.
        desvio = (note["start"] - inicio_batida) / duracao_batida
        if desvio > tolerance:
            continue

        fase = idx % beats_per_measure
        ataques[fase] += 1.0
        duracoes[fase] += (note["end"] - note["start"]) / duracao_batida
        acentos[fase] += float(note.get("amplitude", 0.0) or 0.0)

    if sum(ataques) == 0:
        return None

    def normalizar(valores: list[float]) -> list[float]:
        total = sum(valores)
        return [v / total for v in valores] if total > 0 else [0.0] * len(valores)

    a, d, ac = normalizar(ataques), normalizar(duracoes), normalizar(acentos)
    # Pesos deliberadamente próximos: nenhuma das três evidências é
    # forte o bastante sozinha, e o consenso entre elas é o que dá
    # confiança. Duração pesa um pouco mais por ser a menos sensível a
    # ruído de detecção (amplitude do Basic Pitch varia bastante; a
    # contagem de ataques ignora o quanto a nota "ocupa" o tempo).
    scores = [0.32 * a[i] + 0.40 * d[i] + 0.28 * ac[i] for i in range(beats_per_measure)]

    ordem = sorted(range(beats_per_measure), key=lambda i: scores[i], reverse=True)
    fase = ordem[0]
    margem = scores[ordem[0]] - scores[ordem[1]]

    # Primeira batida real com essa fase, a partir do começo da melodia.
    primeira_nota = melody[0]["start"]
    idx_inicial = _beat_index_at(primeira_nota, beat_times)
    idx_forte = idx_inicial
    while idx_forte % beats_per_measure != fase:
        idx_forte += 1
        if idx_forte >= len(beat_times):
            return None
    downbeat_time = beat_times[idx_forte]

    anacrusis = sum(1 for n in melody if n["start"] < downbeat_time - 1e-6)

    return {
        "phase": fase,
        "downbeat_time": downbeat_time,
        "scores": scores,
        "margin": margem,
        "anacrusis_notes": anacrusis,
    }
