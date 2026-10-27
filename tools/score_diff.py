#!/usr/bin/env python3
"""Compara duas partituras MusicXML por compasso, sem modificar as fontes.

Uso: python3 tools/score_diff.py anterior.musicxml revisada.musicxml

Compara notação, não áudio nem fidelidade à imagem. Ignora coordenadas,
paginação, cor e IDs gráficos do exportador. Para comparar um .mscz, exporte
primeiro uma cópia MusicXML no MuseScore; este módulo não abre nem salva .mscz.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 32 * 1024 * 1024
CATEGORIES = ("alturas", "ritmo", "ornamentos", "ligacoes", "cifras", "textos", "barras", "estrutura")


def _leaf_texts(element: ET.Element, skip: frozenset[str] = frozenset()) -> tuple:
    """Representação dos conteúdos, sem coordenadas/atributos de gravura."""
    return tuple(
        (node.tag, (node.text or "").strip())
        for node in element.iter()
        if node is not element and node.tag not in skip and not list(node)
    )


def _pitch(note: ET.Element) -> tuple:
    if note.find("rest") is not None:
        return ("pausa",)
    pitch = note.find("pitch")
    if pitch is not None:
        return ("nota", pitch.findtext("step"), pitch.findtext("alter", "0"), pitch.findtext("octave"))
    unpitched = note.find("unpitched")
    if unpitched is not None:
        return ("percussao", unpitched.findtext("display-step"), unpitched.findtext("display-octave"))
    return ("sem_altura",)


def _duration(note: ET.Element, divisions: int) -> Fraction | None:
    value = note.findtext("duration")
    return Fraction(int(value), divisions) if value is not None else None


def _notation(note: ET.Element, names: set[str]) -> tuple:
    result = []
    for parent in note.findall("notations"):
        for child in parent.iter():
            if child.tag in names:
                # O número interno pode mudar numa nova exportação; a posição
                # da nota e start/stop são o que importa para esta triagem.
                result.append((child.tag, child.get("type"), (child.text or "").strip()))
    return tuple(result)


@dataclass(frozen=True)
class MeasureDigest:
    alturas: tuple
    ritmo: tuple
    ornamentos: tuple
    ligacoes: tuple
    cifras: tuple
    textos: tuple
    barras: tuple
    estrutura: tuple


def _digest(measure: ET.Element, divisions: int) -> tuple[MeasureDigest, int]:
    alturas, ritmo, ornamentos, ligacoes = [], [], [], []
    cifras, textos, barras, estrutura = [], [], [], []
    for child in measure:
        if child.tag == "attributes":
            value = child.findtext("divisions")
            if value is not None:
                divisions = int(value)
                if divisions <= 0:
                    raise ValueError(f"divisions inválido no compasso {measure.get('number')}")
            parts = []
            for node in child:
                if node.tag not in {"divisions", "staves"}:
                    parts.append((node.tag, _leaf_texts(node)))
            if parts:
                estrutura.extend(parts)
        elif child.tag == "note":
            voice = child.findtext("voice", "1")
            staff = child.findtext("staff", "1")
            grace = child.find("grace")
            identity = (voice, staff, child.find("chord") is not None)
            alturas.append((identity, _pitch(child)))
            ritmo.append((identity, _duration(child, divisions), child.findtext("type"),
                          len(child.findall("dot")),
                          (grace.get("slash") if grace is not None else None),
                          _leaf_texts(child.find("time-modification"))
                          if child.find("time-modification") is not None else ()))
            ornaments = _notation(child, {"staccato", "staccatissimo", "tenuto", "accent",
                                          "strong-accent", "detached-legato", "fermata",
                                          "harmonic", "trill-mark", "mordent", "inverted-mordent"})
            # Outros símbolos notacionais não se perdem silenciosamente.
            other = tuple((el.tag, el.get("type"), (el.text or "").strip())
                          for parent in child.findall("notations") for el in parent.iter()
                          if el.tag not in {"notations", "articulations", "technical", "ornaments",
                                              "tied", "slur", "glissando", "slide"}
                          and el.tag not in {item[0] for item in ornaments})
            accidental = child.find("accidental")
            written_accidental = (
                (accidental.text or "").strip(), accidental.get("cautionary"),
                accidental.get("editorial")) if accidental is not None else None
            if ornaments or other or child.find("notehead") is not None or written_accidental:
                ornamentos.append((len(alturas), ornaments, other,
                                   child.findtext("notehead"), written_accidental))
            links = _notation(child, {"tied", "slur", "glissando", "slide"})
            ties = tuple(el.get("type") for el in child.findall("tie"))
            if links or ties:
                ligacoes.append((len(alturas), links, ties))
        elif child.tag == "harmony":
            cifras.append(_leaf_texts(child, frozenset({"offset", "staff"})))
        elif child.tag == "direction":
            semantic = []
            for node in child:
                if node.tag in {"direction-type", "sound", "offset"}:
                    semantic.append((node.tag, _leaf_texts(node) if list(node) else tuple(sorted(node.attrib.items()))))
            if semantic:
                textos.append(tuple(semantic))
        elif child.tag == "barline":
            barras.append((child.get("location"), _leaf_texts(child)))
    digest = MeasureDigest(*(tuple(group) for group in
                             (alturas, ritmo, ornamentos, ligacoes, cifras, textos, barras, estrutura)))
    return digest, divisions


def read_score(path: Path) -> dict[tuple[str, str], MeasureDigest]:
    """Lê MusicXML partwise plano; cada chave é (parte, compasso)."""
    if path.suffix.lower() not in {".musicxml", ".xml"}:
        raise ValueError("use um arquivo MusicXML plano (.musicxml ou .xml)")
    if path.stat().st_size > MAX_XML_BYTES:
        raise ValueError("MusicXML acima do limite de 32 MiB")
    root = ET.parse(path).getroot()
    if root.tag != "score-partwise":
        raise ValueError("somente MusicXML score-partwise é suportado")
    result = {}
    for part in root.findall("part"):
        part_id = part.get("id")
        if not part_id:
            raise ValueError("parte sem id no MusicXML")
        divisions = 1
        for measure in part.findall("measure"):
            number = measure.get("number")
            if not number:
                raise ValueError(f"compasso sem número na parte {part_id}")
            key = (part_id, number)
            if key in result:
                raise ValueError(f"compasso duplicado: {part_id}/{number}")
            result[key], divisions = _digest(measure, divisions)
    return result


def compare_scores(before: dict, after: dict) -> dict[tuple[str, str], tuple[str, ...]]:
    def measure_order(key: tuple[str, str]) -> tuple:
        match = re.fullmatch(r"(\d+)(.*)", key[1])
        return (key[0], int(match.group(1)) if match else float("inf"),
                match.group(2) if match else key[1])

    changes = {}
    for key in sorted(before.keys() | after.keys(), key=measure_order):
        if key not in before:
            changes[key] = ("compasso_adicionado",)
        elif key not in after:
            changes[key] = ("compasso_removido",)
        else:
            kinds = tuple(name for name in CATEGORIES if getattr(before[key], name) != getattr(after[key], name))
            if kinds:
                changes[key] = kinds
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anterior", type=Path)
    parser.add_argument("revisada", type=Path)
    args = parser.parse_args(argv)
    try:
        old, new = read_score(args.anterior), read_score(args.revisada)
        changes = compare_scores(old, new)
    except (OSError, ValueError, ET.ParseError) as exc:
        parser.error(str(exc))
    print(f"Compassos: {len(old)} anterior / {len(new)} revisada; diferenças musicais: {len(changes)}")
    for (part, measure), categories in changes.items():
        print(f"{part} compasso {measure}: {', '.join(categories)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
