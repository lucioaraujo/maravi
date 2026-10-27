"""Nomes de pauta e timbres MIDI declarados pelo músico, não detectados."""

# (nome da parte, nome MusicXML, programa MIDI 0-based, programa XML 1-based)
SCORE_INSTRUMENTS = {
    "melody": ("Melodia", None, 0, None),
    "piano": ("Piano", "Piano", 0, 1),
    "piano_grand": ("Piano", "Piano", 0, 1),
    "flute": ("Flauta", "Flute", 73, 74),
    "violin": ("Violino", "Violin", 40, 41),
    "voice": ("Voz", "Voice", 53, 54),
}
