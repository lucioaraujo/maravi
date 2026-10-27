# Maravi — notas técnicas de instalação (Linux, Python 3.12)

> **Para instalar o Maravi, use o [`INSTALL.md`](INSTALL.md)** (quatro
> línguas). Este arquivo guarda as notas técnicas do desenvolvimento: a
> combinação de dependências, a receita do pacote e os testes de fumaça.
> Desde a v0.1.0 (27 out. 2026), o pacote Linux é montado pela CI do
> repositório em Ubuntu 22.04; as menções abaixo à "candidata local" são o
> histórico de antes da release.

Este guia reproduz a combinação usada no computador de desenvolvimento em
20 out. 2026, reinstalada em venv Linux limpo em 23 out. 2026. Isso valida
o caminho Linux local, não transforma a candidata em release. Não há `.deb`,
AppImage, instalador Windows/macOS nem serviço público nesta etapa.

## Entrada comum e estado multiplataforma

`run_maravi.py` inicia a interface somente em `127.0.0.1`, sem recarregador
de desenvolvimento. Com um ambiente Python **já preparado**, o comando é
`.venv/bin/python run_maravi.py` no Linux/macOS e
`.venv\Scripts\python.exe run_maravi.py` no Windows. A porta pode ser
alterada com `MARAVI_PORT` (1024–65535). Isso padroniza a inicialização do
código-fonte; **não é um instalador** e não demonstra que o pipeline de áudio
funciona nos três sistemas.

Para PDF/imagem, Audiveris e MuseScore Studio precisam ser instalados
separadamente. Se não estiverem no `PATH`, use `MARAVI_AUDIVERIS_BIN` e
`MARAVI_MUSESCORE_BIN` apontando para seus executáveis. O ImageMagick moderno
é chamado por `magick identify` e `magick convert` quando disponível; no
Windows não se usa `convert.exe`, que também nomeia um utilitário do sistema.
`pdfinfo`/`pdfseparate` (Poppler) e `ffmpeg` ainda precisam estar no `PATH`.
O OMR em Windows/macOS não foi testado em máquinas reais.

O manifesto abaixo é um instantâneo **Linux/Python 3.12**, não um lockfile
multiplataforma. O Basic Pitch 0.4.0 declara oficialmente até Python 3.11 no
seu projeto, enquanto esta instalação Linux usa Python 3.12 com ONNX e
`--no-deps`; essa exceção ainda não foi reproduzida no Windows/macOS. Não
copiar o manifesto Linux cegamente para gerar `.exe` ou `.app`. Cada sistema
precisa de resolução de dependências, teste de instalação limpa, teste de
áudio e auditoria de licenças antes de receber um pacote público.

Pré-requisitos: Python 3.12 com `venv`, `pip` e `ffmpeg` acessível no terminal.
O Maravi usa `ffmpeg` para converter áudio do microfone e como fallback para
arquivos que o decodificador direto não abre. A interface atual é um servidor
Flask **local**, acessível somente em `127.0.0.1:5001`.

Na pasta do Maravi:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-local-linux-py312.txt
.venv/bin/python -m pip install --no-deps basic-pitch==0.4.0
.venv/bin/python -c 'from basic_pitch import ONNX_PRESENT, ICASSP_2022_MODEL_PATH; from basic_pitch.inference import predict; assert ONNX_PRESENT and ICASSP_2022_MODEL_PATH.is_file()'
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python run_maravi.py
```

No Linux, se houver uma cópia local extraída do Audiveris no caminho
`.local-build/audiveris-5.11.0/root/opt/audiveris/bin/Audiveris`, o atalho
`./run_maravi.sh` configura `MARAVI_AUDIVERIS_BIN` somente para esse processo
e inicia a mesma interface local. A variável explícita definida pelo usuário
tem precedência; sem a cópia local, o script usa uma instalação de sistema
encontrada normalmente pelo Maravi. O script não instala dependências nem
abre a porta para a rede externa.

Depois, abra `http://127.0.0.1:5001` no navegador. Se a porta 5001 já estiver
ocupada, inicie o Maravi numa porta local alternativa, por exemplo:

```bash
MARAVI_PORT=5052 .venv/bin/python webapp/app.py
```

Nesse caso, abra `http://127.0.0.1:5052/` e use a mesma porta para `/ajuda`.
O servidor local iniciado por `webapp/app.py` recarrega automaticamente o
código Python quando ele muda; templates são relidos e a interface não usa
cache persistente. Depois de iniciar esta versão, F5 mostra as próximas
mudanças de HTML, CSS e JavaScript. Um servidor antigo, já em execução, precisa
ser encerrado uma vez com Ctrl+C no terminal e iniciado novamente; F5 não
troca de servidor nem de porta sozinho. Para confirmar a página atual, procure
“Canal esquerdo” e a opção “Este áudio já contém somente o instrumento
escolhido” no formulário de áudio.
Para partitura impressa, abra `/partitura` na mesma porta. Esse caminho
experimental requer, além das dependências do áudio, `pdfinfo` e `pdfseparate`
(Poppler), `identify` e `convert` (ImageMagick), Audiveris e MuseScore no sistema. O Audiveris é
opcional para iniciar o webapp: sem ele, a página mostra a dependência e não
permite enviar a partitura. Se o executável não estiver no `PATH`, configure
`MARAVI_AUDIVERIS_BIN` com seu caminho absoluto antes de iniciar o servidor.
O pacote `.deb` oficial instala o executável em
`/opt/audiveris/bin/Audiveris`, detectado automaticamente pelo Maravi; um
caminho configurado sem permissão de execução é rejeitado. A edição Flatpak
do Audiveris não é suportada automaticamente pelo adaptador atual.
Instalação e formatos oficiais do Audiveris:
<https://github.com/Audiveris/audiveris/releases>.
O Maravi não instala o Audiveris nem baixa dados de idioma. O Audiveris
oferece download opcional de dados de OCR ao ser iniciado pelo usuário.
Créditos, licenças e limites de redistribuição: [CREDITS.md](CREDITS.md).
Em 21 out. 2026, Audiveris 5.11.0 foi extraído temporariamente do `.deb`
oficial Ubuntu 24.04 e testado, sem instalação global. Para repetir o teste
de fumaça depois de instalar ou apontar o executável oficial, use:

```bash
timeout 120 .venv/bin/python tools/smoke_omr_real.py
timeout 120 .venv/bin/python tools/smoke_omr_real.py --format png
timeout 120 .venv/bin/python tools/smoke_omr_real.py --format jpg
timeout 120 .venv/bin/python tools/smoke_omr_real.py --format tif
timeout 120 .venv/bin/python tools/smoke_omr_real.py --pages 2
timeout 120 .venv/bin/python tools/smoke_omr_real.py --pages 2 --selected-page 2
timeout 120 .venv/bin/python tools/smoke_omr_real.py --format webp
```

O script usa uma partitura autoral de teste, diretórios temporários privados e
não substitui uma revisão musical. Para um binário fora do caminho oficial,
defina `MARAVI_AUDIVERIS_BIN` com seu caminho absoluto. O adaptador executa
Audiveris em modo Java headless, com heap padrão de 1536 MiB; respeita um
`-Xmx` já presente em `JAVA_TOOL_OPTIONS`. Os testes não tinham dados de
idioma OCR instalados: a leitura de letras e outros textos segue sem validação.
PDF, PNG, JPG/JPEG, TIFF, WebP, BMP, GIF estático, HEIC/HEIF e AVIF são aceitos
um arquivo por vez. O limite é 20 MB por arquivo e 16 megapixels por página
de imagem. PDFs podem ser lidos inteiros até 8 páginas ou em uma página
específica, inclusive quando o documento tem mais de 8 páginas. O PDF original
permanece no job e a página escolhida é extraída numa cópia separada.
WebP/BMP/GIF/HEIC/HEIF/AVIF são convertidos em PNG de trabalho com limites de
memória, disco e tempo; exigem decodificador ImageMagick para o formato na
máquina local. GIF animado ou arquivo de imagem com várias cenas não entra
nesse caminho: use PDF/TIFF multipágina. O MusicXML exportado é limitado a
32 MiB antes da leitura pelo Maravi. O MusicXML e o MIDI resultantes são
rascunhos e devem ser comparados com a fonte no MuseScore.
Não use `--host 0.0.0.0`
nem exponha a porta ao exterior: uploads e jobs ainda não têm as proteções de
um serviço público. Os resultados ficam temporariamente em
`/tmp/maravi_webapp_jobs/`; a versão atual **não** os expira automaticamente.
O tutorial de gravação, transcrição e revisão da partitura está em
`http://127.0.0.1:5001/ajuda`, depois de iniciar o servidor. O formulário de
áudio e suas mensagens de navegador podem ser usados com `?lang=pt|en|fr|es`.
O tutorial tem guias nesses quatro idiomas, com diferentes níveis de detalhe.
A entrada PDF/imagem, os resultados OMR e de áudio, erros frequentes e a
confirmação de exportação usam PT/EN/FR/ES e preservam o idioma nos links.
Avisos estruturais do Audiveris e detalhes técnicos de exceções permanecem em
português, identificados como tal. Em 23 out. 2026, a entrada PDF/imagem foi
inspecionada visualmente em Chromium desktop nos quatro idiomas e em francês
numa largura móvel de 390 px. Isso não substitui revisão em Firefox, inspeção
das páginas de resultado/erro, conferência linguística por falantes ou teste
interativo de envio.
Não coloque áudios privados num servidor compartilhado. O conteúdo gerado
nessa pasta só deve ser limpo depois de confirmar que os jobs terminaram e que
os arquivos não precisam ser preservados.

O Basic Pitch 0.4.0 declara TensorFlow como dependência obrigatória no
metadata do pacote. Nesta instalação ele é deliberadamente instalado com
`--no-deps` **depois** das dependências pinadas, pois a inferência usa o modelo
ONNX incluído no Basic Pitch e `onnxruntime`; TensorFlow não está instalado.
Por isso `pip check` ainda reporta TensorFlow ausente, embora o import e o
modelo ONNX tenham sido verificados no venv limpo Linux. Não esconder esse
aviso nem inferir compatibilidade em outros sistemas a partir do teste Linux.

O arquivo de versões é um instantâneo do ambiente, sem hashes de wheels e sem
auditoria completa das licenças transitivas. Antes de publicar uma versão
instalável: verificar uma gravação autorizada do upload ao MusicXML/MIDI,
registrar tempo/RAM, conferir a partitura no MuseScore e revisar avisos/licenças
das dependências distribuídas.

## Candidata Linux local, ainda não distribuível

Em 23 out. 2026, um venv Linux/Python 3.12 novo instalou esse manifesto e
Basic Pitch 0.4.0 com `--no-deps`. Na verificação mais recente passaram 92
testes Python e 2 JavaScript; o smoke test da candidata congelada repetiu a
interface e fluxos WAV/OGG sintéticos até MusicXML/MIDI. OMR com
Audiveris 5.11.0 externo e MuseScore externo passou no PDF autoral de uma
página (8 compassos; comparação estrutural sem diferenças nesse exemplo).
Uma candidata PyInstaller `onedir` de aproximadamente 391 MB respondeu a
`--version` e repetiu, fora da árvore do projeto, a interface local e os dois
fluxos de áudio. Isso não valida qualidade musical, instalação em outra
distribuição Linux, Windows ou macOS.

Para repetir o build **sem ZIP e sem sobrescrever outro build**, instale
`pyinstaller==6.22.3` e `pyinstaller-hooks-contrib==2026.9` no mesmo venv
Linux e execute da pasta Maravi:

```bash
.venv/bin/python -B packaging/build_linux.py
```

O script cria um diretório exclusivo em `.local-build/maravi-linux-build-*`
no disco do projeto (ignorado pelo Git), com
executável, código e modelo ONNX, `LICENSE`, `CREDITS.md` e avisos das wheels
em `THIRD_PARTY_NOTICES/`. Esse script foi verificado sintaticamente e o
coletor de avisos foi testado separadamente. Em 23 out. 2026, a receita
automatizada foi executada ponta a ponta e a saída passou nos testes de
interface, pré-análise, WAV, microfone OGG e PDF/OMR autoral (com Audiveris
e MuseScore externos). A saída permanece local; não a mova
para Downloads nem a publique como release sem fechar a auditoria de licenças
e testar a candidata resultante. O script recusa o build com menos de 5 GiB
livres em `/` ou menos de 2 GiB no disco do projeto; ainda é necessário fazer
o preflight completo de RAM/swap/processos da governança RASGO. A limpeza do
venv/build de ensaio em `/tmp` deixou 7,7 GB livres em `/` na última checagem.
O teste funcional é:

```bash
.venv/bin/python -B tools/smoke_frozen_server.py /caminho/da/candidata/Maravi-0.1.0-linux-x86_64
```

Com Audiveris e MuseScore instalados/configurados, acrescente `--with-omr`
ao comando para incluir PDF impresso, MXL/OMR e MusicXML/MIDI. O teste usa
`tests/fixtures/omr_smoke.musicxml`, partitura autoral curta. Não executa
revisão musical de material real do usuário.

A candidata desta máquina foi produzida em Linux Mint 22 (glibc 2.39).
`THIRD_PARTY_NOTICES/ABI_REPORT.json` foi gerado na inspeção da candidata:
o maior símbolo exigido é `GLIBC_2.39`, em `libmvec.so.1`. A receita agora
gera esse relatório automaticamente e requer `readelf`/binutils. Um símbolo
requerido não prova compatibilidade com uma distribuição; indica apenas um
limite a verificar. Não anunciar suporte a Linux mais antigo sem reconstruir
numa base adequada e testar em instalação independente.
O relatório foi exercitado na candidata existente após o build, sem gerar
outra candidata apenas para repetir o teste.

Audiveris, MuseScore, FFmpeg, Poppler e ImageMagick **não** são embutidos
nesse build: a pessoa precisa instalá-los separadamente para as funções que
os requerem. O inventário da candidata de 23 out. 2026 encontrou 47
distribuições Python, 100 avisos/licenças, 248 entradas nativas e símbolo
glibc máximo 2.39. `flatbuffers` declara Apache 2.0, mas não traz arquivo
LICENSE separado. NumPy/SciPy, bibliotecas nativas e modelo ONNX ainda exigem
auditoria específica. Ver `CREDITS.md`. O smoke test
passou na cópia executada em `/tmp`; não houve teste de instalação
independente nem aprovação para distribuição.
