# Installing Maravi

**English** · [Português](#português) · [Français](#français) · [Español](#español)

Maravi 0.1.1 ships as a package for **Linux x86_64**. It runs on your
computer: a small local server on `127.0.0.1` and your browser as the
interface. Nothing is sent over the network.

## Requirements

- Linux x86_64 with glibc 2.35 or newer: Ubuntu 22.04 or newer, Linux Mint
  21 or newer, Debian 12 or newer, Fedora, Arch, openSUSE Tumbleweed.
- A web browser (Firefox, Chromium, Chrome).
- About 1 GB free on disk (the unpacked package takes ~400 MB).
- **FFmpeg** (required: Maravi uses it to read audio files).
- Only to read printed scores (PDF or image), optionally: **Audiveris**,
  **MuseScore**, **Poppler** and **ImageMagick**.

Windows and macOS are not supported in this version.

## Step by step

1. Install FFmpeg:
   - Ubuntu, Mint, Debian: `sudo apt install ffmpeg`
   - Fedora: enable RPM Fusion, then `sudo dnf install ffmpeg`
   - Arch: `sudo pacman -S ffmpeg`
2. Download `maravi-0.1.1-linux-x86_64.tar.xz` from
   [Releases](https://github.com/lucioaraujo/maravi/releases/latest). To
   check the download, compare it with the `.sha256` file:
   `sha256sum -c maravi-0.1.1-linux-x86_64.tar.xz.sha256`
3. Unpack it where you keep your programs, for example your home folder:
   `tar -xf maravi-0.1.1-linux-x86_64.tar.xz`
4. Start it: `./maravi-0.1.1-linux-x86_64/maravi`
   The browser opens at `http://127.0.0.1:5001/`. If it does not, open that
   address yourself.
5. To stop Maravi, press Ctrl+C in the terminal (or close it).

If port 5001 is busy, choose another one:
`MARAVI_PORT=5052 ./maravi-0.1.1-linux-x86_64/maravi`

### Reading printed scores (optional)

The "PDF / image" page needs four more programs. Without them Maravi still
works for audio, and the page says what is missing.

- Ubuntu, Mint, Debian: `sudo apt install poppler-utils imagemagick musescore3`
  (or MuseScore 4 from [musescore.org](https://musescore.org/))
- Audiveris: download the package for your system from
  [Audiveris releases](https://github.com/Audiveris/audiveris/releases)
  (for Ubuntu, the `.deb`). Maravi finds `/opt/audiveris/bin/Audiveris` by
  itself; for another place, start Maravi with
  `MARAVI_AUDIVERIS_BIN=/path/to/Audiveris`.
- If MuseScore is not on your `PATH`, use `MARAVI_MUSESCORE_BIN`.

### Your files

Each job lives in a temporary folder (`/tmp/maravi_webapp_jobs/`), shown on
the result page. The system may clear it on restart. **Save or download your
MusicXML and MIDI before closing.** Maravi never changes the file you chose.

### Uninstall

Delete the `maravi-0.1.1-linux-x86_64` folder. Maravi writes nothing else
outside the temporary folder.

## From source

For developers, on any system with Python 3.12 (tested only on Linux):

```bash
git clone https://github.com/lucioaraujo/maravi.git && cd maravi
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-local-linux-py312.txt
.venv/bin/python -m pip install --no-deps basic-pitch==0.4.0
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python run_maravi.py
```

Technical notes (dependencies, the package recipe, smoke tests):
[`INSTALL_LOCAL.md`](INSTALL_LOCAL.md), in Portuguese.

---

## Português

O Maravi 0.1.1 sai como pacote para **Linux x86_64**. Roda no seu
computador: um pequeno servidor local em `127.0.0.1` e o navegador como
interface. Nada é enviado pela rede.

**Requisitos:** Linux x86_64 com glibc 2.35 ou mais nova (Ubuntu 22.04+,
Linux Mint 21+, Debian 12+, Fedora, Arch, openSUSE Tumbleweed); um
navegador; cerca de 1 GB livre em disco (o pacote aberto ocupa ~400 MB); o
**FFmpeg** (obrigatório, para ler os arquivos de áudio). Só para ler
partituras impressas, opcionais: **Audiveris**, **MuseScore**, **Poppler** e
**ImageMagick**. Windows e macOS não têm suporte nesta versão.

**Passo a passo:**

1. Instale o FFmpeg: Ubuntu, Mint, Debian: `sudo apt install ffmpeg`;
   Fedora: ative o RPM Fusion e `sudo dnf install ffmpeg`; Arch:
   `sudo pacman -S ffmpeg`.
2. Baixe `maravi-0.1.1-linux-x86_64.tar.xz` em
   [Releases](https://github.com/lucioaraujo/maravi/releases/latest). Para
   conferir o download: `sha256sum -c maravi-0.1.1-linux-x86_64.tar.xz.sha256`
3. Descompacte onde guarda seus programas, por exemplo na pasta pessoal:
   `tar -xf maravi-0.1.1-linux-x86_64.tar.xz`
4. Abra: `./maravi-0.1.1-linux-x86_64/maravi`. O navegador abre em
   `http://127.0.0.1:5001/`; se não abrir, digite esse endereço.
5. Para fechar, Ctrl+C no terminal (ou feche o terminal).

Se a porta 5001 estiver ocupada:
`MARAVI_PORT=5052 ./maravi-0.1.1-linux-x86_64/maravi`

**Partituras impressas (opcional).** A página "PDF / imagem" precisa de mais
quatro programas; sem eles, o áudio funciona e a página diz o que falta.
Ubuntu, Mint, Debian: `sudo apt install poppler-utils imagemagick musescore3`
(ou o MuseScore 4 de [musescore.org](https://musescore.org/)). O Audiveris vem
das [releases do Audiveris](https://github.com/Audiveris/audiveris/releases)
(no Ubuntu, o `.deb`); o Maravi acha `/opt/audiveris/bin/Audiveris` sozinho,
e para outro lugar use `MARAVI_AUDIVERIS_BIN=/caminho/do/Audiveris`. Para o
MuseScore fora do `PATH`, `MARAVI_MUSESCORE_BIN`.

**Seus arquivos.** Cada trabalho fica numa pasta temporária
(`/tmp/maravi_webapp_jobs/`), mostrada na página do resultado, que o sistema
pode limpar ao reiniciar. **Guarde ou baixe o MusicXML e o MIDI antes de
fechar.** O arquivo que você escolheu nunca é alterado.

**Desinstalar:** apague a pasta `maravi-0.1.1-linux-x86_64`. **A partir do
código** (desenvolvedores, Python 3.12): veja [From source](#from-source).

---

## Français

Maravi 0.1.1 est distribué en paquet pour **Linux x86_64**. Il fonctionne
sur votre ordinateur : un petit serveur local sur `127.0.0.1` et le
navigateur comme interface. Rien n'est envoyé sur le réseau.

**Configuration requise :** Linux x86_64 avec glibc 2.35 ou plus récente
(Ubuntu 22.04+, Linux Mint 21+, Debian 12+, Fedora, Arch, openSUSE
Tumbleweed) ; un navigateur ; environ 1 Go libre (le paquet décompressé
occupe ~400 Mo) ; **FFmpeg** (obligatoire, pour lire les fichiers audio).
Seulement pour lire des partitions imprimées, facultatifs : **Audiveris**,
**MuseScore**, **Poppler** et **ImageMagick**. Windows et macOS ne sont pas
pris en charge dans cette version.

**Pas à pas :**

1. Installez FFmpeg : Ubuntu, Mint, Debian : `sudo apt install ffmpeg` ;
   Fedora : activez RPM Fusion puis `sudo dnf install ffmpeg` ; Arch :
   `sudo pacman -S ffmpeg`.
2. Téléchargez `maravi-0.1.1-linux-x86_64.tar.xz` dans
   [Releases](https://github.com/lucioaraujo/maravi/releases/latest). Pour
   vérifier : `sha256sum -c maravi-0.1.1-linux-x86_64.tar.xz.sha256`
3. Décompressez-le, par exemple dans votre dossier personnel :
   `tar -xf maravi-0.1.1-linux-x86_64.tar.xz`
4. Lancez : `./maravi-0.1.1-linux-x86_64/maravi`. Le navigateur s'ouvre sur
   `http://127.0.0.1:5001/` ; sinon, saisissez cette adresse.
5. Pour l'arrêter, Ctrl+C dans le terminal (ou fermez-le).

Si le port 5001 est occupé :
`MARAVI_PORT=5052 ./maravi-0.1.1-linux-x86_64/maravi`

**Partitions imprimées (facultatif).** La page « PDF / image » demande
quatre programmes de plus ; sans eux, l'audio fonctionne et la page indique
ce qui manque. Ubuntu, Mint, Debian :
`sudo apt install poppler-utils imagemagick musescore3` (ou MuseScore 4 sur
[musescore.org](https://musescore.org/)). Audiveris se télécharge dans les
[releases d'Audiveris](https://github.com/Audiveris/audiveris/releases) (le
`.deb` sous Ubuntu) ; Maravi trouve `/opt/audiveris/bin/Audiveris` tout seul,
sinon utilisez `MARAVI_AUDIVERIS_BIN=/chemin/vers/Audiveris`. Pour MuseScore
hors du `PATH`, `MARAVI_MUSESCORE_BIN`.

**Vos fichiers.** Chaque travail vit dans un dossier temporaire
(`/tmp/maravi_webapp_jobs/`), indiqué sur la page du résultat, que le système
peut vider au redémarrage. **Enregistrez ou téléchargez le MusicXML et le
MIDI avant de fermer.** Le fichier choisi n'est jamais modifié.

**Désinstaller :** supprimez le dossier `maravi-0.1.1-linux-x86_64`. **Depuis
le code source** (développeurs, Python 3.12) : voir
[From source](#from-source).

---

## Español

Maravi 0.1.1 se distribuye como paquete para **Linux x86_64**. Funciona en
su computadora: un pequeño servidor local en `127.0.0.1` y el navegador como
interfaz. Nada se envía por la red.

**Requisitos:** Linux x86_64 con glibc 2.35 o más reciente (Ubuntu 22.04+,
Linux Mint 21+, Debian 12+, Fedora, Arch, openSUSE Tumbleweed); un
navegador; cerca de 1 GB libre en disco (el paquete descomprimido ocupa
~400 MB); **FFmpeg** (obligatorio, para leer los archivos de audio). Solo
para leer partituras impresas, opcionales: **Audiveris**, **MuseScore**,
**Poppler** e **ImageMagick**. Windows y macOS no tienen soporte en esta
versión.

**Paso a paso:**

1. Instale FFmpeg: Ubuntu, Mint, Debian: `sudo apt install ffmpeg`; Fedora:
   active RPM Fusion y `sudo dnf install ffmpeg`; Arch:
   `sudo pacman -S ffmpeg`.
2. Descargue `maravi-0.1.1-linux-x86_64.tar.xz` en
   [Releases](https://github.com/lucioaraujo/maravi/releases/latest). Para
   verificar: `sha256sum -c maravi-0.1.1-linux-x86_64.tar.xz.sha256`
3. Descomprima, por ejemplo en su carpeta personal:
   `tar -xf maravi-0.1.1-linux-x86_64.tar.xz`
4. Abra: `./maravi-0.1.1-linux-x86_64/maravi`. El navegador se abre en
   `http://127.0.0.1:5001/`; si no, escriba esa dirección.
5. Para cerrarlo, Ctrl+C en la terminal (o cierre la terminal).

Si el puerto 5001 está ocupado:
`MARAVI_PORT=5052 ./maravi-0.1.1-linux-x86_64/maravi`

**Partituras impresas (opcional).** La página «PDF / imagen» necesita cuatro
programas más; sin ellos, el audio funciona y la página indica lo que falta.
Ubuntu, Mint, Debian: `sudo apt install poppler-utils imagemagick musescore3`
(o MuseScore 4 de [musescore.org](https://musescore.org/)). Audiveris se
descarga en las [releases de Audiveris](https://github.com/Audiveris/audiveris/releases)
(el `.deb` en Ubuntu); Maravi encuentra `/opt/audiveris/bin/Audiveris` solo,
y para otra ubicación use `MARAVI_AUDIVERIS_BIN=/ruta/a/Audiveris`. Para
MuseScore fuera del `PATH`, `MARAVI_MUSESCORE_BIN`.

**Sus archivos.** Cada trabajo queda en una carpeta temporal
(`/tmp/maravi_webapp_jobs/`), indicada en la página del resultado, que el
sistema puede vaciar al reiniciar. **Guarde o descargue el MusicXML y el
MIDI antes de cerrar.** El archivo que usted eligió nunca se modifica.

**Desinstalar:** borre la carpeta `maravi-0.1.1-linux-x86_64`. **Desde el
código fuente** (desarrolladores, Python 3.12): vea
[From source](#from-source).
