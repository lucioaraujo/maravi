"""Células melódicas: onde uma ideia começa, se desenvolve e termina.

Autor, 2026-08-31: "as notas estão relativamente certas, com poucos ou
quase nenhum erro, porém os tempos ainda precisa melhorar. principalmente
se o maravi passar a ser inteligente no aspecto de reconhecer as
narrativas melódicas, o início de uma célula melódica, seu
desenvolvimento e fim."

## Por que isto ataca o problema de TEMPO, não o de altura

O erro relatado antes: "uma mesma ideia musical é repetida uma segunda
vez, porém o maravi não reconheceu a repetição e escreveu começando em
outro ponto do compasso". Medido no áudio de referência (`ParMePerdre`):
o tema de abertura reaparece 5 vezes e cai em 5 posições métricas
diferentes (25, 37, 12, 32, 4 de 48 ticks por compasso). Em tempo
absoluto a primeira repetição é de 8,007 compassos - exata; as
seguintes escorregam ~0,3 compasso. A grade detectada tem 2 intervalos
de batida anômalos em 308, e cada batida perdida/inserida desloca meio
compasso em 2/4.

Ou seja: as ALTURAS estão certas e o que erra é a fase da grade. Uma
célula melódica quase sempre COMEÇA num ponto métrico definido (tempo
forte, ou uma anacruse regular até ele) - então saber onde as células
começam é saber onde as barras de compasso deveriam cair. É a mesma
observação que o autor tinha feito antes: "o importante na maioria das
melodias é definir onde é o tempo forte [...] identificar isso facilita
a escrita musical".

## Método: LBDM (Local Boundary Detection Model)

Cambouropoulos (2001) - a formalização computável das *grouping
preference rules* de Lerdahl & Jackendoff (GTTM, 1983). O projeto já
cita GTTM como raiz acadêmica, mas do lado GERATIVO
(`ANTITOTEM/docs/PESQUISA_ACENTUACAO_GENERATIVA.md`, e o
`phraseProgress`/"clímax de frase" de `PESQUISA_MELODIA_GENERATIVA.md`).
O ANTITOTEM sabe onde a frase começa porque ele mesmo a gerou; o MARAVI
precisa inferir do áudio - mesma teoria, sentido inverso, exatamente a
dualidade desenhada na seção 4.4 do `MARAVI_CONCEITO.md`.

É baseado em regras, sem modelo treinado - a mesma direção declarada no
Marco 2 (reduzir dependência de modelo de terceiro).

A intuição do LBDM é a de Gestalt: percebemos fronteira onde há
MUDANÇA. Para cada uma de três dimensões - salto de altura, intervalo
entre ataques, e pausa entre notas - mede-se (a) o quanto o valor muda
de um par de notas para o seguinte e (b) o tamanho absoluto do valor.
Uma fronteira forte é onde um valor grande coincide com uma mudança
grande: um salto melódico depois de graus conjuntos, uma nota longa
depois de curtas, um silêncio.
"""
from __future__ import annotations

# Pesos das três dimensões. Cambouropoulos propõe dar mais peso ao
# intervalo entre ataques (o ritmo agrupa mais fortemente que a altura),
# e é o que se usa aqui. Não foram calibrados por escuta neste projeto -
# são o ponto de partida da literatura, a ajustar contra material real.
WEIGHT_PITCH = 0.25
WEIGHT_IOI = 0.50
WEIGHT_REST = 0.25


def _degrees_of_change(values: list[float]) -> list[float]:
    """Grau de mudança entre valores vizinhos, normalizado: 0 = iguais,
    1 = um é zero e o outro não. Fórmula do LBDM."""
    out = []
    for i in range(len(values) - 1):
        a, b = values[i], values[i + 1]
        soma = a + b
        out.append(abs(a - b) / soma if soma > 0 else 0.0)
    return out


def _boundary_strength(values: list[float]) -> list[float]:
    """Força de fronteira por dimensão: cada valor pesa pelo quanto ele
    difere dos vizinhos dos dois lados. Um valor grande cercado de
    valores parecidos não é fronteira; um valor grande logo após valores
    pequenos é."""
    if len(values) < 2:
        return [0.0] * len(values)
    graus = _degrees_of_change(values)
    forcas = []
    for i in range(len(values)):
        antes = graus[i - 1] if i > 0 else 0.0
        depois = graus[i] if i < len(graus) else 0.0
        forcas.append(values[i] * (antes + depois))
    total = max(forcas) if forcas else 0.0
    return [f / total for f in forcas] if total > 0 else forcas


def detect_cells(melody: list[dict], threshold: float = 0.30) -> dict:
    """Segmenta a melodia em células. Devolve `{boundaries, strengths,
    cells}`, onde `boundaries` são índices de nota que INICIAM uma
    célula (0 sempre é fronteira) e `cells` são pares (início, fim)
    exclusivos no fim.

    `threshold`: força mínima (0..1) pra um pico contar como fronteira.
    Mais baixo = células menores e mais numerosas.
    """
    n = len(melody)
    if n < 3:
        return {"boundaries": [0], "strengths": [0.0] * n, "cells": [(0, n)] if n else []}

    # As três dimensões do LBDM, alinhadas por índice de nota.
    saltos = [0.0]
    ioi = [0.0]
    pausas = [0.0]
    for i in range(1, n):
        saltos.append(abs(float(melody[i]["pitch"]) - float(melody[i - 1]["pitch"])))
        ioi.append(max(0.0, float(melody[i]["start"]) - float(melody[i - 1]["start"])))
        pausas.append(max(0.0, float(melody[i]["start"]) - float(melody[i - 1]["end"])))

    fp = _boundary_strength(saltos)
    fi = _boundary_strength(ioi)
    fr = _boundary_strength(pausas)
    forcas = [WEIGHT_PITCH * fp[i] + WEIGHT_IOI * fi[i] + WEIGHT_REST * fr[i] for i in range(n)]

    # Fronteira = pico local acima do limiar. Exigir pico local (e não só
    # "acima do limiar") evita marcar várias fronteiras seguidas dentro
    # de uma mesma transição forte.
    boundaries = [0]
    for i in range(1, n - 1):
        if forcas[i] >= threshold and forcas[i] >= forcas[i - 1] and forcas[i] >= forcas[i + 1]:
            if i - boundaries[-1] >= 2:  # célula de 1 nota só não é célula
                boundaries.append(i)

    cells = [(boundaries[k], boundaries[k + 1] if k + 1 < len(boundaries) else n) for k in range(len(boundaries))]
    return {"boundaries": boundaries, "strengths": forcas, "cells": cells}


def metric_positions(
    boundaries: list[int],
    melody: list[dict],
    beat_times: list[float],
    beats_per_measure: int,
    anchor_time: float,
    ticks_per_beat: int = 24,
) -> list[int]:
    """Posição métrica (tick dentro do compasso) em que cada célula
    começa. É a MEDIDA que interessa: se as células começassem sempre no
    mesmo lugar do compasso, a grade estaria coerente. Dispersão alta
    aqui é a assinatura do problema de fase relatado pelo autor."""
    from beat_grid import time_to_step

    passos_por_compasso = ticks_per_beat * beats_per_measure
    ancora = time_to_step(anchor_time, beat_times, ticks_per_beat)
    posicoes = []
    for b in boundaries:
        passo = time_to_step(melody[b]["start"], beat_times, ticks_per_beat) - ancora
        posicoes.append(int(round(passo)) % passos_por_compasso)
    return posicoes
