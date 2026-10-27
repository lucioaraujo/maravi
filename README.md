# Maravi

**English** · [Português](#português) · [Français](#français) · [Español](#español)

Maravi turns recorded melodies into readable scores. It is a device of the
[RASGO](https://rasgoinstruments.arquiviagem.net/) family by Lúcio de Araújo:
not an instrument that makes sound, but a tool for listening, study and
notation. It runs on your own computer, in your browser; nothing is sent to
any server.

**Version:** v0.1.0 · **License:** GNU AGPL-3.0-or-later (see
[`LICENSE`](LICENSE)) · **Tested on:** Linux x86_64

## What it does

- **Audio → score.** From a recording of a melody (voice, flute, violin, a
  single line), Maravi proposes a MusicXML score and a MIDI file. You choose
  the staff instrument (Melody, Piano, Flute, Violin or Voice) and say whether
  the source is already isolated. If you leave tempo or key blank, it offers a
  pre-analysis of the first 20 seconds, which you can correct before writing.
- **Printed score → MusicXML/MIDI.** From a PDF or an image (PNG, JPG, TIFF)
  of a printed score, Maravi reads the music with Audiveris and exports
  MusicXML and MIDI with MuseScore. This part is optional and needs both
  programs installed.
- **Readable writing.** The goal is a score a person can read and play: the
  essential melody, written clearly, without inventing ornaments. Options:
  "solo legato" (joins fragments of the same pitch), writing by phrases, a
  conservative octave review for solo flute, choosing the left or right
  channel of a stereo file.
- **Interface** in Portuguese, English, French and Spanish, with a tutorial.

## What it does not do (yet)

- It does not separate instruments in a mix, nor recognise which instrument
  is playing. With an orchestral recording, the result is a *hypothesis* of
  the melody.
- "Piano, two staves" is an experiment: it distributes notes by register, it
  does not find the real hands.
- **Every result needs human review** in a score editor (MuseScore or
  similar): pitch, rhythm, meter and phrasing.
- Windows and macOS have not been tested.

## Install

Linux x86_64: download `maravi-0.1.0-linux-x86_64.tar.gz` from the
[Releases](https://github.com/lucioaraujo/maravi/releases) page and follow
[`INSTALL.md`](INSTALL.md). FFmpeg is required; Audiveris, MuseScore,
Poppler and ImageMagick are only needed to read printed scores.

From source (any system with Python 3.12, untested outside Linux): see
[`INSTALL.md`](INSTALL.md#from-source).

## Your files

Maravi works locally, on `127.0.0.1`. Each job lives in a temporary folder
(shown on the result page) inside your system's temporary directory, which
the system may clear on restart. **Save or download your MusicXML and MIDI
before closing.** Maravi never touches the original file you chose. The
rights of the scores and recordings you use remain yours, or their authors'.

## Credits

Conception and development: Lúcio de Araújo. Maravi relies on free software
by others (Spotify Basic Pitch, librosa, Audiveris, MuseScore and more),
each with its own license: see [`CREDITS.md`](CREDITS.md).

---

## Português

Maravi transforma gravações de melodias em partituras legíveis. É um
dispositivo da família [RASGO](https://rasgoinstruments.arquiviagem.net/), de
Lúcio de Araújo: não é um instrumento que produz som, mas uma ferramenta de
escuta, estudo e notação. Roda no seu computador, no navegador; nada é
enviado a servidor algum.

**Versão:** v0.1.0 · **Licença:** GNU AGPL-3.0-or-later · **Testado em:** Linux x86_64

**O que faz.** De uma gravação de melodia (voz, flauta, violino, uma linha),
propõe uma partitura MusicXML e um MIDI; você escolhe o instrumento da pauta
e diz se a fonte já está isolada; sem andamento ou tom, oferece uma
pré-análise dos primeiros 20 segundos, que você corrige antes de escrever. De
um PDF ou imagem de partitura impressa, lê a música com o Audiveris e
exporta com o MuseScore (opcional, com os dois instalados). O objetivo é uma
partitura que se leia e se toque: a melodia essencial, escrita com clareza,
sem inventar ornamentos. Interface em português, inglês, francês e espanhol,
com tutorial.

**O que ainda não faz.** Não separa instrumentos numa mistura nem reconhece o
instrumento; numa gravação orquestral, o resultado é uma *hipótese* da
melodia. "Piano, duas pautas" é um ensaio. **Todo resultado pede revisão
humana** num editor de partituras. Windows e macOS não foram testados.

**Instalar:** o pacote Linux está em
[Releases](https://github.com/lucioaraujo/maravi/releases); passo a passo em
[`INSTALL.md`](INSTALL.md#português). O FFmpeg é obrigatório; Audiveris,
MuseScore, Poppler e ImageMagick só para ler partituras impressas.

**Seus arquivos.** Tudo é local, em `127.0.0.1`. Cada trabalho fica numa
pasta temporária do sistema, que pode ser limpa ao reiniciar: **guarde ou
baixe o MusicXML e o MIDI antes de fechar.** O arquivo original nunca é
tocado, e os direitos das partituras e gravações continuam seus ou dos seus
autores. Créditos em [`CREDITS.md`](CREDITS.md).

---

## Français

Maravi transforme des enregistrements de mélodies en partitions lisibles.
C'est un dispositif de la famille [RASGO](https://rasgoinstruments.arquiviagem.net/),
de Lúcio de Araújo : pas un instrument qui produit du son, mais un outil
d'écoute, d'étude et de notation. Il fonctionne sur votre ordinateur, dans
le navigateur ; rien n'est envoyé à un serveur.

**Version :** v0.1.0 · **Licence :** GNU AGPL-3.0-or-later · **Testé sous :** Linux x86_64

**Ce qu'il fait.** À partir de l'enregistrement d'une mélodie (voix, flûte,
violon, une seule ligne), il propose une partition MusicXML et un MIDI ; vous
choisissez l'instrument de la portée et indiquez si la source est déjà
isolée ; sans tempo ni tonalité, il propose une pré-analyse des 20 premières
secondes, que vous corrigez avant l'écriture. À partir d'un PDF ou d'une
image de partition imprimée, il lit la musique avec Audiveris et exporte
avec MuseScore (facultatif, les deux installés). Le but est une partition
qu'on lit et qu'on joue : la mélodie essentielle, écrite clairement, sans
ornements inventés. Interface en portugais, anglais, français et espagnol,
avec un tutoriel.

**Ce qu'il ne fait pas encore.** Il ne sépare pas les instruments d'un
mélange et ne reconnaît pas l'instrument ; avec un enregistrement
orchestral, le résultat est une *hypothèse* de la mélodie. « Piano, deux
portées » est un essai. **Tout résultat demande une relecture humaine**
dans un éditeur de partitions. Windows et macOS n'ont pas été testés.

**Installer :** le paquet Linux est dans
[Releases](https://github.com/lucioaraujo/maravi/releases) ; pas à pas dans
[`INSTALL.md`](INSTALL.md#français). FFmpeg est nécessaire ; Audiveris,
MuseScore, Poppler et ImageMagick seulement pour lire les partitions
imprimées.

**Vos fichiers.** Tout reste local, sur `127.0.0.1`. Chaque travail vit dans
un dossier temporaire du système, qui peut être vidé au redémarrage :
**enregistrez ou téléchargez le MusicXML et le MIDI avant de fermer.** Le
fichier d'origine n'est jamais modifié, et les droits des partitions et
enregistrements restent les vôtres ou ceux de leurs auteurs. Crédits dans
[`CREDITS.md`](CREDITS.md).

---

## Español

Maravi transforma grabaciones de melodías en partituras legibles. Es un
dispositivo de la familia [RASGO](https://rasgoinstruments.arquiviagem.net/),
de Lúcio de Araújo: no es un instrumento que produce sonido, sino una
herramienta de escucha, estudio y notación. Funciona en su computadora, en
el navegador; nada se envía a ningún servidor.

**Versión:** v0.1.0 · **Licencia:** GNU AGPL-3.0-or-later · **Probado en:** Linux x86_64

**Qué hace.** A partir de la grabación de una melodía (voz, flauta, violín,
una sola línea), propone una partitura MusicXML y un MIDI; usted elige el
instrumento del pentagrama e indica si la fuente ya está aislada; sin tempo
ni tonalidad, ofrece un preanálisis de los primeros 20 segundos, que usted
corrige antes de escribir. A partir de un PDF o una imagen de partitura
impresa, lee la música con Audiveris y exporta con MuseScore (opcional, con
ambos instalados). El objetivo es una partitura que se lea y se toque: la
melodía esencial, escrita con claridad, sin inventar ornamentos. Interfaz en
portugués, inglés, francés y español, con tutorial.

**Qué aún no hace.** No separa instrumentos en una mezcla ni reconoce el
instrumento; con una grabación orquestal, el resultado es una *hipótesis* de
la melodía. «Piano, dos pentagramas» es un ensayo. **Todo resultado requiere
revisión humana** en un editor de partituras. Windows y macOS no se han
probado.

**Instalar:** el paquete Linux está en
[Releases](https://github.com/lucioaraujo/maravi/releases); paso a paso en
[`INSTALL.md`](INSTALL.md#español). FFmpeg es obligatorio; Audiveris,
MuseScore, Poppler e ImageMagick solo para leer partituras impresas.

**Sus archivos.** Todo es local, en `127.0.0.1`. Cada trabajo queda en una
carpeta temporal del sistema, que puede vaciarse al reiniciar: **guarde o
descargue el MusicXML y el MIDI antes de cerrar.** El archivo original nunca
se modifica, y los derechos de las partituras y grabaciones siguen siendo
suyos o de sus autores. Créditos en [`CREDITS.md`](CREDITS.md).
