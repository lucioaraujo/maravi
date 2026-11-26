# Installing Maravi

**English** · [Português](#português) · [Français](#français) · [Español](#español)

Maravi 0.1.2 offers three formats for **Linux x86_64**. It runs on your
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

1. Open [Maravi 0.1.2 on GitHub](https://github.com/lucioaraujo/maravi/releases/tag/v0.1.2).
   If you download all three packages, save `SHA256SUMS` in the same
   folder and run `sha256sum -c SHA256SUMS`. For one download, compare
   its `sha256sum` output with the corresponding line.
2. Choose one format:
   - **Debian, Ubuntu and Mint (.deb):** run `sudo apt install ./maravi-0.1.2-linux-x86_64.deb`
     in your download folder. This installs FFmpeg and adds Maravi to
     the applications menu. You can also run `maravi` in a terminal.
   - **AppImage:** install FFmpeg for your distribution. Run
     `chmod +x maravi-0.1.2-linux-x86_64.AppImage`, then
     `./maravi-0.1.2-linux-x86_64.AppImage`. If FUSE is unavailable,
     add `--appimage-extract-and-run` to the command.
   - **Install for your user (.tar.gz):** install FFmpeg and Python 3.
     Extract `maravi-0.1.2-linux-x86_64.tar.gz`, enter the extracted
     folder, and run `./install.sh`. Open Maravi from the applications
     menu or run `~/.local/bin/maravi`.
3. The browser opens at `http://127.0.0.1:5001/`. If it does not, open
   that address. To stop Maravi, press Ctrl+C or close its terminal.

For the AppImage or `.tar.gz`, install FFmpeg with `sudo apt install ffmpeg`
on Debian, Ubuntu and Mint, `sudo dnf install ffmpeg` with RPM Fusion on
Fedora, or `sudo pacman -S ffmpeg` on Arch. If port 5001 is busy, prefix
the launch command with `MARAVI_PORT=5052`.

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

For the Debian package, run `sudo apt remove maravi`. For AppImage, delete
its file. For a user installation, run `./install.sh --remove` from the
extracted archive folder.

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

O Maravi 0.1.2 oferece três formatos para **Linux x86_64**. Roda no seu
computador: um pequeno servidor local em `127.0.0.1` e o navegador como
interface. Nada é enviado pela rede.

**Requisitos:** Linux x86_64 com glibc 2.35 ou mais nova (Ubuntu 22.04+,
Linux Mint 21+, Debian 12+, Fedora, Arch, openSUSE Tumbleweed); um
navegador; cerca de 1 GB livre em disco (o pacote aberto ocupa ~400 MB); o
**FFmpeg** (obrigatório, para ler os arquivos de áudio). Só para ler
partituras impressas, opcionais: **Audiveris**, **MuseScore**, **Poppler** e
**ImageMagick**. Windows e macOS não têm suporte nesta versão.

**Passo a passo:**

1. Abra a [versão 0.1.2 do Maravi no GitHub](https://github.com/lucioaraujo/maravi/releases/tag/v0.1.2).
   Se baixar os três pacotes, salve `SHA256SUMS` na mesma pasta e rode
   `sha256sum -c SHA256SUMS`. Para um único download, compare o resultado
   do `sha256sum` com a linha correspondente.
2. Escolha um formato:
   - **Debian, Ubuntu e Mint (.deb):** na pasta de downloads, rode
     `sudo apt install ./maravi-0.1.2-linux-x86_64.deb`. O pacote instala
     o FFmpeg e adiciona o Maravi ao menu. Também dá para rodar
     `maravi` no terminal.
   - **AppImage:** instale o FFmpeg da sua distribuição. Rode
     `chmod +x maravi-0.1.2-linux-x86_64.AppImage` e
     `./maravi-0.1.2-linux-x86_64.AppImage`. Se o FUSE não estiver
     disponível, acrescente `--appimage-extract-and-run` ao comando.
   - **Instalação para seu usuário (.tar.gz):** instale o FFmpeg e o
     Python 3. Extraia `maravi-0.1.2-linux-x86_64.tar.gz`, entre na
     pasta extraída e rode `./install.sh`. Abra pelo menu ou rode
     `~/.local/bin/maravi`.
3. O navegador abre em `http://127.0.0.1:5001/`. Se não abrir, digite
   o endereço. Para fechar o Maravi, pressione Ctrl+C ou feche o terminal
   dele.

No AppImage ou `.tar.gz`, instale o FFmpeg com `sudo apt install ffmpeg`
no Debian, Ubuntu e Mint, `sudo dnf install ffmpeg` com o RPM Fusion no
Fedora ou `sudo pacman -S ffmpeg` no Arch. Se a porta 5001 estiver ocupada,
coloque `MARAVI_PORT=5052` antes do comando que abre o programa.

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

**Desinstalar:** no Debian, rode `sudo apt remove maravi`. Para o AppImage,
apague o arquivo. Na instalação para seu usuário, rode `./install.sh --remove`
na pasta extraída. **A partir do código** (desenvolvedores, Python 3.12):
veja [From source](#from-source).

---

## Français

Maravi 0.1.2 propose trois formats pour **Linux x86_64**. Il fonctionne
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

1. Ouvrez la [version 0.1.2 de Maravi sur GitHub](https://github.com/lucioaraujo/maravi/releases/tag/v0.1.2).
   Si vous téléchargez les trois paquets, placez `SHA256SUMS` dans le
   même dossier et lancez `sha256sum -c SHA256SUMS`. Pour un seul fichier,
   comparez le résultat de `sha256sum` avec la ligne correspondante.
2. Choisissez un format :
   - **Debian, Ubuntu et Mint (.deb) :** dans le dossier de téléchargement,
     lancez `sudo apt install ./maravi-0.1.2-linux-x86_64.deb`. Le paquet
     installe FFmpeg et ajoute Maravi au menu. Vous pouvez aussi lancer
     `maravi` dans un terminal.
   - **AppImage :** installez FFmpeg pour votre distribution. Exécutez
     `chmod +x maravi-0.1.2-linux-x86_64.AppImage`, puis
     `./maravi-0.1.2-linux-x86_64.AppImage`. Si FUSE est indisponible,
     ajoutez `--appimage-extract-and-run` à la commande.
   - **Installation pour votre compte (.tar.gz) :** installez FFmpeg
     et Python 3. Extrayez `maravi-0.1.2-linux-x86_64.tar.gz`, ouvrez
     le dossier extrait et lancez `./install.sh`. Ouvrez Maravi depuis
     le menu ou lancez `~/.local/bin/maravi`.
3. Le navigateur s’ouvre à `http://127.0.0.1:5001/`. Sinon, saisissez
   cette adresse. Pour arrêter Maravi, appuyez sur Ctrl+C ou fermez
   son terminal.

Pour l’AppImage ou le `.tar.gz`, installez FFmpeg avec `sudo apt install ffmpeg`
sur Debian, Ubuntu et Mint, `sudo dnf install ffmpeg` avec RPM Fusion sur
Fedora, ou `sudo pacman -S ffmpeg` sur Arch. Si le port 5001 est occupé,
placez `MARAVI_PORT=5052` avant la commande de lancement.

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

**Désinstaller :** pour le paquet Debian, lancez `sudo apt remove maravi`.
Pour l’AppImage, supprimez le fichier. Pour l’installation utilisateur,
lancez `./install.sh --remove` depuis le dossier extrait. **Depuis le code
source** (développeurs, Python 3.12) : voir [From source](#from-source).

---

## Español

Maravi 0.1.2 ofrece tres formatos para **Linux x86_64**. Funciona en
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

1. Abra la [versión 0.1.2 de Maravi en GitHub](https://github.com/lucioaraujo/maravi/releases/tag/v0.1.2).
   Si descarga los tres paquetes, guarde `SHA256SUMS` en la misma carpeta
   y ejecute `sha256sum -c SHA256SUMS`. Para un solo archivo, compare
   el resultado de `sha256sum` con la línea correspondiente.
2. Elija un formato:
   - **Debian, Ubuntu y Mint (.deb):** en la carpeta de descargas, ejecute
     `sudo apt install ./maravi-0.1.2-linux-x86_64.deb`. El paquete
     instala FFmpeg y añade Maravi al menú. También puede ejecutar
     `maravi` en un terminal.
   - **AppImage:** instale FFmpeg para su distribución. Ejecute
     `chmod +x maravi-0.1.2-linux-x86_64.AppImage` y después
     `./maravi-0.1.2-linux-x86_64.AppImage`. Si FUSE no está disponible,
     añada `--appimage-extract-and-run` al comando.
   - **Instalación para su usuario (.tar.gz):** instale FFmpeg y Python 3.
     Extraiga `maravi-0.1.2-linux-x86_64.tar.gz`, entre en la carpeta
     extraída y ejecute `./install.sh`. Abra Maravi desde el menú o
     ejecute `~/.local/bin/maravi`.
3. El navegador abre `http://127.0.0.1:5001/`. Si no se abre, escriba
   esa dirección. Para cerrar Maravi, pulse Ctrl+C o cierre su terminal.

Para AppImage o `.tar.gz`, instale FFmpeg con `sudo apt install ffmpeg`
en Debian, Ubuntu y Mint, `sudo dnf install ffmpeg` con RPM Fusion en
Fedora o `sudo pacman -S ffmpeg` en Arch. Si el puerto 5001 está ocupado,
ponga `MARAVI_PORT=5052` antes del comando de inicio.

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

**Desinstalar:** para el paquete Debian, ejecute `sudo apt remove maravi`.
Para AppImage, borre el archivo. Si instaló para su usuario, ejecute
`./install.sh --remove` en la carpeta extraída. **Desde el código fuente**
(desarrolladores, Python 3.12): vea [From source](#from-source).
