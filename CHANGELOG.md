# Changelog

## 0.1.1 — a smaller package, 2026-10-27

- **The download goes from 157 to 112 MiB.** The package is now
  compressed with xz: `maravi-0.1.1-linux-x86_64.tar.xz`, opened with
  `tar -xf`. The program inside is exactly the same.
- Nothing else changes in the transcription.

## 0.1.0 — first public version, 2026-10-27

The first public version of Maravi: recorded melodies into readable scores,
on your own computer.

- **Audio → MusicXML and MIDI** for single melodies (voice, flute, violin,
  one line), with the staff instrument chosen by you (Melody, Piano, Flute,
  Violin, Voice), an optional pre-analysis of tempo and key, "solo legato",
  writing by phrases, a conservative octave review for solo flute and the
  choice of the left or right channel of a stereo file.
- **Printed score (PDF or image) → MusicXML and MIDI** through Audiveris and
  MuseScore, when both are installed (optional).
- **Interface** in Portuguese, English, French and Spanish, with a tutorial;
  the browser opens by itself when Maravi starts.
- **Package** for Linux x86_64 (`.tar.gz`, built on Ubuntu 22.04, glibc
  2.35 or newer), with the third-party notices. See `INSTALL.md`.

**Stated limitations:** no separation of instruments in a mix and no
recognition of the instrument; "Piano, two staves" is an experiment; every
result needs human review in a score editor; Windows and macOS untested.

The development history up to 2026-10-27 is kept in the author's private
monorepo (`rasgo-instruments`, last Maravi commit `e09f94e`).
