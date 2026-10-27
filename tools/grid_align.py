"""Re-ajuste da grade rítmica usando a própria música como referência.

Autor, 2026-08-31: "as notas estão relativamente certas [...] porém os
tempos ainda precisa melhorar" e "uma mesma ideia musical é repetida uma
segunda vez, porém o maravi não reconheceu a repetição da ideia, e
escreveu começando em outro ponto do compasso".

## O princípio

Se uma ideia melódica se repete, as ocorrências têm que cair na MESMA
posição do compasso - e o intervalo entre elas tem que ser um número
INTEIRO de compassos. Quando não é, quem errou foi a grade, não a
música. Medição em `MARAVI_CONCEITO.md` seção 12.4: o tema de abertura
do áudio de referência reaparece 5 vezes e cai em 5 posições métricas
diferentes; a 1ª repetição está a 8,007 compassos da primeira (exata),
as seguintes escorregam ~0,3 compasso cada - **desvio gradual**, o
rastreamento de andamento do `librosa.beat.beat_track` escorregando ao
longo da peça.

Este módulo não conserta "a fase num ponto" (já testado e descartado, ver
seção 12.4). Ele usa as repetições detectadas como **âncoras de tempo
absolutas** e re-deriva a grade de batidas inteira de forma que os
intervalos entre âncoras virem números inteiros de compassos, com
interpolação suave entre âncoras. É a seção 10 do conceito ("estrutura
serviria como validação de bugs de alinhamento") virada de diagnóstico
em correção.

## Opt-in, nunca padrão

Muda TODA a escrita rítmica. Só roda com `--align-repeats` explícito na
CLI (ou a caixa correspondente no webapp). Sem repetições detectáveis, é
no-op - devolve a grade original intocada e diz por quê.
"""
from __future__ import annotations

import bisect


def find_repeated_themes(
    melody: list[dict],
    min_notes: int = 12,
    min_occurrences: int = 3,
) -> list[dict]:
    """Acha sequências de altura que se repetem LITERALMENTE na melodia.

    Devolve uma lista de `{pitches, onsets}`, uma por tema, `onsets` sendo
    os instantes (segundos) em que cada ocorrência COMEÇA. Ordenada do
    tema mais longo pro mais curto (o mais longo é o mais confiável como
    âncora - coincidência de 16 alturas seguidas é improvável).

    Só altura, não ritmo: duas execuções da mesma frase podem ter micro-
    variações de duração, mas a sequência de notas é a assinatura
    estável. É a mesma lógica de `merge_fragmented_repeats` no sentido
    inverso - lá se junta o que foi partido, aqui se reconhece o que
    volta.
    """
    pitches = [int(n["pitch"]) for n in melody]
    starts = [float(n["start"]) for n in melody]
    n = len(pitches)
    if n < min_notes * min_occurrences:
        return []

    # Cresce o comprimento enquanto ainda houver alguma sequência com
    # `min_occurrences` cópias - assim pega o tema mais longo possível
    # sem varrer todos os comprimentos.
    best_by_length: dict[int, list[tuple]] = {}
    length = min_notes
    while length <= n // min_occurrences:
        seen: dict[tuple, list[int]] = {}
        for i in range(n - length + 1):
            seen.setdefault(tuple(pitches[i : i + length]), []).append(i)
        repeats = {seq: idxs for seq, idxs in seen.items() if len(idxs) >= min_occurrences}
        if not repeats:
            break
        best_by_length[length] = sorted(repeats.items(), key=lambda kv: -len(kv[1]))
        length += 2

    if not best_by_length:
        return []

    temas: list[dict] = []
    usados: set[int] = set()  # índices de nota já cobertos por um tema mais longo
    for length in sorted(best_by_length, reverse=True):
        for seq, idxs in best_by_length[length]:
            # Descarta ocorrências que se sobrepõem a um tema já aceito
            # (mais longo) ou entre si.
            limpas: list[int] = []
            for i in sorted(idxs):
                if any(j in usados for j in range(i, i + length)):
                    continue
                if limpas and i < limpas[-1] + length:
                    continue
                limpas.append(i)
            if len(limpas) < min_occurrences:
                continue
            for i in limpas:
                usados.update(range(i, i + length))
            temas.append({"pitches": list(seq), "onsets": [starts[i] for i in limpas]})
    return temas


def _measure_seconds(beat_times: list[float], beats_per_measure: int) -> float:
    """Duração média de um compasso na grade atual - só pra dar uma
    escala inicial ao arredondamento dos intervalos entre âncoras."""
    total_beats = len(beat_times) - 1
    if total_beats <= 0:
        return 0.0
    return ((beat_times[-1] - beat_times[0]) / total_beats) * beats_per_measure


def align_grid_to_repeats(
    beat_times: list[float],
    melody: list[dict],
    beats_per_measure: int,
    min_notes: int = 12,
    max_local_stretch: float = 0.18,
) -> dict:
    """Devolve `{beat_times, anchors, applied, reason, before, after}`.

    `applied=False` (e `beat_times` inalterado) quando não há repetições
    confiáveis, ou quando a correção necessária excederia
    `max_local_stretch` (18% de variação de andamento entre âncoras é o
    máximo plausível - acima disso é mais provável que a detecção de
    repetição esteja errada do que a música ter mudado tanto de
    andamento).

    `anchors`: lista de `(tempo_segundos, compasso_alvo)` usada.
    `before`/`after`: coerência métrica (fração de ocorrências de tema na
    mesma posição do compasso) antes e depois - pra decidir se valeu.
    """
    temas_todos = find_repeated_themes(melody, min_notes=min_notes)
    if not temas_todos:
        return {
            "beat_times": beat_times,
            "anchors": [],
            "applied": False,
            "reason": "nenhuma ideia melódica se repete o bastante pra servir de âncora",
            "before": None,
            "after": None,
        }

    escala = _measure_seconds(beat_times, beats_per_measure)
    if escala <= 0:
        return {
            "beat_times": beat_times, "anchors": [], "applied": False,
            "reason": "grade de batidas degenerada", "before": None, "after": None,
        }

    # SÓ usa como âncora um tema cujos intervalos entre ocorrências JÁ
    # estão perto de um número inteiro de compassos na grade atual
    # (resíduo < 0,12). Se o intervalo já é ~8,02 compassos, arredondar
    # pra 8 é uma correção pequena e confiável; se é 16,62, o "16 ou 17?"
    # é um chute, e forçar qualquer um dos dois warpa a grade por meio
    # compasso pra satisfazer um pressuposto que pode ser falso.
    #
    # Medido no áudio de referência (`MARAVI_CONCEITO.md` 12.4): dos 5
    # temas literais detectados, só o de abertura tem gaps quase-inteiros
    # (8,02 e 8,05); os outros vão de 0,20 a 0,43 de resíduo. Usar todos
    # levou a coerência de repetição a 100% MAS piorou um sinal
    # independente (fronteiras de célula LBDM em posição forte: 26%→12%)
    # - overfit ao próprio objetivo.
    temas: list[dict] = []
    for tema in temas_todos:
        ons = tema["onsets"]
        if len(ons) < 2:
            continue
        residuos = [abs(g / escala - round(g / escala)) for g in (ons[i] - ons[i - 1] for i in range(1, len(ons)))]
        if all(r < 0.12 for r in residuos):
            temas.append(tema)

    if not temas:
        return {
            "beat_times": beat_times, "anchors": [], "applied": False,
            "reason": (
                f"{len(temas_todos)} tema(s) repetido(s) detectado(s), mas nenhum com intervalos "
                "próximos o bastante de um nº inteiro de compassos pra ser âncora confiável "
                "(ver MARAVI_CONCEITO.md 12.4)"
            ),
            "before": None, "after": None,
        }

    ancoras_brutas: list[tuple[float, int]] = []
    for tid, tema in enumerate(temas):
        for t in tema["onsets"]:
            ancoras_brutas.append((t, tid))
    ancoras_brutas.sort()

    # Constrói os pares (tempo, compasso_alvo). O primeiro tema fixa a
    # origem: sua 1a ocorrência é o compasso 0.0 (fracionário - pode
    # começar no meio de um compasso, é a mesma posição toda vez). Cada
    # âncora seguinte recebe o compasso alvo = compasso da anterior +
    # round((dt)/escala), o intervalo arredondado pro inteiro de
    # compassos mais próximo.
    pares: list[tuple[float, float]] = [(ancoras_brutas[0][0], 0.0)]
    for i in range(1, len(ancoras_brutas)):
        t_prev, _ = ancoras_brutas[i - 1]
        t_cur, _ = ancoras_brutas[i]
        dt = t_cur - t_prev
        n_compassos = round(dt / escala)
        if n_compassos < 1:
            n_compassos = 1
        pares.append((t_cur, pares[-1][1] + n_compassos))

    # Verifica se a correção é plausível: entre cada par de âncoras, o
    # quanto a duração-de-compasso local teria que mudar.
    for i in range(1, len(pares)):
        (t0, m0), (t1, m1) = pares[i - 1], pares[i]
        if m1 <= m0:
            continue
        dur_local = (t1 - t0) / (m1 - m0)
        if abs(dur_local - escala) / escala > max_local_stretch:
            return {
                "beat_times": beat_times, "anchors": pares, "applied": False,
                "reason": (
                    f"correção exigiria andamento local {abs(dur_local - escala) / escala * 100:.0f}% "
                    f"fora da média (limite {max_local_stretch * 100:.0f}%) - detecção de repetição "
                    "provavelmente errada"
                ),
                "before": None, "after": None,
            }

    # Estende as âncoras até cobrir a peça inteira: uma no começo
    # (compasso negativo, extrapolando a 1a duração local) e uma no fim.
    (ta, ma), (tb, mb) = pares[0], pares[1] if len(pares) > 1 else pares[0]
    dur0 = (tb - ta) / (mb - ma) if len(pares) > 1 and mb > ma else escala
    inicio = melody[0]["start"]
    if inicio < ta:
        pares.insert(0, (inicio, ma - (ta - inicio) / dur0))
    fim = max(n["end"] for n in melody)
    (tp, mp), (tq, mq) = pares[-2], pares[-1]
    durN = (tq - tp) / (mq - mp) if mq > mp else escala
    if fim > tq:
        pares.append((fim, mq + (fim - tq) / durN))

    # Nova grade de batidas: para cada índice de batida j, seu compasso é
    # j/beats_per_measure; o tempo dele é o mapa compasso->tempo
    # (inverso do que construímos) avaliado aí, piecewise-linear entre
    # âncoras.
    compassos_anchor = [m for _, m in pares]
    tempos_anchor = [t for t, _ in pares]

    def compasso_para_tempo(m: float) -> float:
        if m <= compassos_anchor[0]:
            return tempos_anchor[0] + (m - compassos_anchor[0]) * dur0
        if m >= compassos_anchor[-1]:
            return tempos_anchor[-1] + (m - compassos_anchor[-1]) * durN
        k = bisect.bisect_right(compassos_anchor, m) - 1
        k = max(0, min(k, len(pares) - 2))
        m0, m1 = compassos_anchor[k], compassos_anchor[k + 1]
        t0, t1 = tempos_anchor[k], tempos_anchor[k + 1]
        frac = (m - m0) / (m1 - m0) if m1 > m0 else 0.0
        return t0 + frac * (t1 - t0)

    n_batidas = len(beat_times)
    nova_grade = [compasso_para_tempo(j / beats_per_measure) for j in range(n_batidas)]
    # Monotônica por segurança (âncoras fora de ordem não deveriam
    # acontecer, mas um clamp barato evita grade inválida).
    for j in range(1, len(nova_grade)):
        if nova_grade[j] <= nova_grade[j - 1]:
            nova_grade[j] = nova_grade[j - 1] + 1e-4

    antes = _metric_coherence(temas, beat_times, beats_per_measure, melody)
    depois = _metric_coherence(temas, nova_grade, beats_per_measure, melody)

    # O alinhamento DEFINE o tempo forte, e ele precisa ser usado no
    # lugar do `--anacrusis-notes` do autor - senão o escritor de
    # MusicXML quantiza com uma âncora e a grade com outra, e a contagem
    # de compassos descarrila (achado real: 154 compassos de grade
    # viraram 334 na partitura quando a anacruse informada não batia com
    # a origem que o alinhamento fixou). O compasso 0.0 das âncoras é,
    # por construção, o primeiro tempo forte; seu instante é o mapa
    # compasso->tempo avaliado em 0.0.
    downbeat_time = compasso_para_tempo(0.0)
    # Quantas notas caem antes dele - o equivalente ao que
    # `--anacrusis-notes` teria contado.
    anacrusis = sum(1 for n in melody if n["start"] < downbeat_time - 1e-6)

    return {
        "beat_times": nova_grade,
        "anchors": pares,
        "applied": True,
        "reason": f"{len(temas)} tema(s) repetido(s), {len(ancoras_brutas)} âncoras",
        "before": antes,
        "after": depois,
        "downbeat_time": downbeat_time,
        "anacrusis_notes": anacrusis,
    }


def _metric_coherence(
    temas: list[dict],
    beat_times: list[float],
    beats_per_measure: int,
    melody: list[dict],
    ticks_per_beat: int = 24,
) -> float:
    """Fração das ocorrências de tema que caem na MESMA posição do
    compasso que a 1a ocorrência daquele tema. 1.0 = grade perfeitamente
    coerente com a estrutura de repetição da música."""
    from beat_grid import time_to_step

    passos_compasso = ticks_per_beat * beats_per_measure
    acertos = total = 0
    for tema in temas:
        posicoes = [
            round(time_to_step(t, beat_times, ticks_per_beat)) % passos_compasso
            for t in tema["onsets"]
        ]
        if not posicoes:
            continue
        alvo = posicoes[0]
        # Tolera ±1 semicolcheia (6 ticks) de diferença - a mesma frase
        # tocada duas vezes tem micro-variação real de ataque.
        for p in posicoes:
            d = min((p - alvo) % passos_compasso, (alvo - p) % passos_compasso)
            if d <= 6:
                acertos += 1
            total += 1
    return acertos / total if total else 0.0
