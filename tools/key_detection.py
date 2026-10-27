"""Detecção de tom/tonalidade pelo método Krumhansl-Schmuckler.

Registrado em `MARAVI_CONCEITO.md` seção 8 como o item "barato" da lista
de enriquecimento: "compara o histograma de classes de altura da melodia
contra os 24 perfis tonais maior/menor conhecidos - dá pra calcular só
com os pitches que já saem da transcrição, sem dado novo".

Duas consequências práticas na partitura, as duas de LEGIBILIDADE (o
objetivo declarado do projeto - "escreve a essência da melodia", lead
sheet legível, não transcrição ultra-detalhada):

1. **Armadura de clave real.** Antes desta implementação
   `musicxml_writer.write_musicxml()` escrevia `<fifths>0</fifths>`
   fixo - toda partitura saía em dó maior. Numa peça em fá maior isso
   obriga um bemol de cortesia em CADA si; em mi maior, quatro
   sustenidos repetidos peça afora. A armadura certa tira todos eles.
2. **Grafia enarmônica coerente.** `midi_note_to_xml_pitch()` grafava
   todo acidente como sustenido (tabela fixa). Em fá maior a nota 10 é
   si bemol, não lá sustenido; em mi maior a nota 3 é ré sustenido, não
   mi bemol. Quem lê tropeça nisso mesmo quando a altura soa certa.

Nada aqui muda ALTURA nenhuma - só como a mesma altura é escrita.

## Método

Krumhansl & Kessler (1982) mediram experimentalmente, com ouvintes, o
quanto cada uma das 12 classes de altura "pertence" a um contexto tonal
- o resultado são dois perfis de 12 valores (um maior, um menor). O
algoritmo: montar o histograma de classes de altura da peça, girá-lo
pros 12 tônicas possíveis, correlacionar (Pearson) contra os dois
perfis, e ficar com a maior correlação entre as 24 combinações.

Uma escolha de implementação que vale registrar: o histograma é
ponderado por **duração**, não por contagem de ataques. Uma semibreve
em fá pesa mais que uma fusa de passagem em fá sustenido - que é
exatamente a intuição musical de "nota estrutural vs. ornamento" (a
mesma ideia ainda em aberto pra simplificação Real Book, seção 7 do
conceito). Contar ataques trataria as duas igual e deixaria passagens
rápidas cromáticas dominarem a decisão.
"""
from __future__ import annotations

import math

# Perfis Krumhansl-Kessler (1982), índice 0 = tônica.
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

# Armadura (nº de sustenidos positivo / bemóis negativo) por classe de
# altura da tônica. Nos pares enarmônicos escolhemos a grafia com menos
# acidentes: dó sustenido maior (7 sustenidos) vira ré bemol maior (5
# bemóis); ré sustenido menor (6 sustenidos) vira mi bemol menor (6
# bemóis, mesmo número, mas grafia usual). Fá sustenido maior fica em 6
# sustenidos por ser a forma mais comum na prática.
MAJOR_FIFTHS = {0: 0, 1: -5, 2: 2, 3: -3, 4: 4, 5: -1, 6: 6, 7: 1, 8: -4, 9: 3, 10: -2, 11: 5}
MINOR_FIFTHS = {0: -3, 1: 4, 2: -1, 3: -6, 4: 1, 5: -4, 6: 3, 7: -2, 8: 5, 9: 0, 10: -5, 11: 2}

# Nome da tônica derivado da própria armadura, pra nome e grafia nunca
# discordarem entre si (índice = fifths + 7, de -7 a +7).
MAJOR_NAMES = ("Dó♭", "Sol♭", "Ré♭", "Lá♭", "Mi♭", "Si♭", "Fá", "Dó", "Sol", "Ré", "Lá", "Mi", "Si", "Fá♯", "Dó♯")
MINOR_NAMES = ("Lá♭", "Mi♭", "Si♭", "Fá", "Dó", "Sol", "Ré", "Lá", "Mi", "Si", "Fá♯", "Dó♯", "Sol♯", "Ré♯", "Lá♯")


def pitch_class_durations(melody: list[dict]) -> list[float]:
    """Histograma de 12 classes de altura ponderado por duração em
    segundos. `melody` é a mesma lista de dicts do resto do pipeline
    (`start`/`end`/`pitch`)."""
    weights = [0.0] * 12
    for note in melody:
        duration = float(note["end"]) - float(note["start"])
        if duration <= 0:
            continue
        weights[int(note["pitch"]) % 12] += duration
    return weights


def _correlation(xs: list[float], ys: tuple[float, ...]) -> float:
    """Pearson entre o histograma e um perfil. Devolve 0.0 quando um dos
    lados não tem variação nenhuma (ex.: melodia de uma nota só) - sem
    variação não há correlação definida, e 0 faz o candidato perder sem
    quebrar a comparação."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def detect_key(melody: list[dict]) -> dict | None:
    """Devolve o tom mais provável da melodia, ou `None` se não houver
    material suficiente pra decidir (melodia vazia, ou uma classe de
    altura só - aí qualquer tom "explica" igualmente mal).

    Chaves do resultado:
      `tonic_pc`   classe de altura da tônica (0=dó .. 11=si)
      `mode`       "major" ou "minor"
      `fifths`     armadura, direto pro `<fifths>` do MusicXML
      `name`       nome legível, ex. "Fá maior"
      `confidence` correlação do vencedor (0..1); quanto maior, mais o
                   histograma se parece com o perfil daquele tom
      `margin`     distância pro segundo colocado - margem pequena
                   significa ambiguidade real (relativa maior/menor,
                   modulação, cromatismo), não erro
      `runner_up`  nome do segundo colocado, pra registro
    """
    return detect_key_from_weights(pitch_class_durations(melody))


def detect_key_from_weights(weights: list[float]) -> dict | None:
    """Mesma comparação tonal a partir de 12 pesos de classes de altura.

    Permite à pré-análise usar croma de áudio sem fabricar eventos de nota.
    Correlação é semelhança com perfil tonal, não probabilidade calibrada.
    """
    if len(weights) != 12:
        raise ValueError("São necessários 12 pesos de classes de altura.")
    if sum(weights) <= 0 or sum(1 for w in weights if w > 0) < 2:
        return None

    scored: list[tuple[float, int, str]] = []
    for tonic in range(12):
        rotated = weights[tonic:] + weights[:tonic]
        scored.append((_correlation(rotated, MAJOR_PROFILE), tonic, "major"))
        scored.append((_correlation(rotated, MINOR_PROFILE), tonic, "minor"))
    scored.sort(key=lambda item: item[0], reverse=True)

    score, tonic, mode = scored[0]
    fifths = (MAJOR_FIFTHS if mode == "major" else MINOR_FIFTHS)[tonic]
    names = MAJOR_NAMES if mode == "major" else MINOR_NAMES
    label = "maior" if mode == "major" else "menor"

    runner_score, runner_tonic, runner_mode = scored[1]
    runner_fifths = (MAJOR_FIFTHS if runner_mode == "major" else MINOR_FIFTHS)[runner_tonic]
    runner_names = MAJOR_NAMES if runner_mode == "major" else MINOR_NAMES
    runner_label = "maior" if runner_mode == "major" else "menor"

    return {
        "tonic_pc": tonic,
        "mode": mode,
        "fifths": fifths,
        "name": f"{names[fifths + 7]} {label}",
        "confidence": score,
        "margin": score - runner_score,
        "runner_up": f"{runner_names[runner_fifths + 7]} {runner_label}",
    }


def parse_key(text: str) -> dict | None:
    """Interpreta um tom escrito pelo usuário (ex.: "F", "Fá", "Bbm",
    "Lá menor", "C#m") - mesma lógica de `--bpm`: o autor sabendo o tom
    real vale mais que qualquer estimativa. Devolve `None` se não
    reconhecer, pra quem chama cair na detecção automática em vez de
    falhar."""
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None

    lowered = raw.lower().replace("♯", "#").replace("♭", "b")
    mode = "major"
    for suffix in (" menor", " minor", " min", "menor", "minor", "min", "m"):
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            mode = "minor"
            lowered = lowered[: -len(suffix)].strip()
            break
    for suffix in (" maior", " major", " maj", "maior", "major", "maj"):
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            lowered = lowered[: -len(suffix)].strip()
            break

    base_pc = {
        "c": 0, "do": 0, "dó": 0,
        "d": 2, "re": 2, "ré": 2,
        "e": 4, "mi": 4,
        "f": 5, "fa": 5, "fá": 5,
        "g": 7, "sol": 7,
        "a": 9, "la": 9, "lá": 9,
        "b": 11, "si": 11,
    }
    accidental = 0
    while lowered.endswith("#"):
        accidental += 1
        lowered = lowered[:-1]
    while lowered.endswith("b") and lowered not in ("b",):
        accidental -= 1
        lowered = lowered[:-1]
    lowered = lowered.strip()

    if lowered not in base_pc:
        return None
    tonic = (base_pc[lowered] + accidental) % 12

    fifths = (MAJOR_FIFTHS if mode == "major" else MINOR_FIFTHS)[tonic]
    names = MAJOR_NAMES if mode == "major" else MINOR_NAMES
    label = "maior" if mode == "major" else "menor"
    return {
        "tonic_pc": tonic,
        "mode": mode,
        "fifths": fifths,
        "name": f"{names[fifths + 7]} {label}",
        "confidence": None,
        "margin": None,
        "runner_up": None,
    }
