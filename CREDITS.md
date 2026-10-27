# Maravi — créditos e ferramentas externas

Maravi: concepção e desenvolvimento de Lúcio de Araújo. O código próprio é
distribuído sob GNU AGPLv3 ou posterior; ver [LICENSE](LICENSE). Essa licença
não altera os direitos das partituras ou gravações enviadas pelo músico.

## Transcrição de áudio

- [Spotify Basic Pitch](https://github.com/spotify/basic-pitch), Spotify AB —
  propõe notas a partir do áudio. A licença do projeto é
  [Apache 2.0](https://github.com/spotify/basic-pitch/blob/main/LICENSE).
  O Maravi usa a dependência Python e o modelo ONNX do pacote no ambiente
  local; ainda é preciso conferir o manifesto e os avisos exatos de qualquer
  pacote distribuído.
- [librosa](https://github.com/librosa/librosa), equipe librosa — análise de
  áudio, pulso e alturas; licença
  [ISC](https://github.com/librosa/librosa/blob/main/LICENSE.md).
- [FFmpeg](https://ffmpeg.org/) — conversão local de formatos de áudio.
  É uma ferramenta externa; a licença efetiva depende da compilação e dos
  componentes incluídos, a auditar antes de redistribuí-la.

## Fontes da interface

O app embute três fontes livres, em `webapp/static/fonts/`, todas sob a
[SIL Open Font License 1.1](https://openfontlicense.org); o texto da licença
e as linhas de copyright estão em
[`webapp/static/fonts/OFL.txt`](webapp/static/fonts/OFL.txt) e seguem no pacote.

- [Fraunces](https://github.com/undercasetype/Fraunces) — © 2020 The Fraunces
  Project Authors (Undercase Type).
- [Work Sans](https://github.com/weiweihuanghuang/Work-Sans) — © 2019 The Work
  Sans Project Authors (Wei Huang).
- [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) — © 2020 The
  JetBrains Mono Project Authors.

## Leitura de partituras impressas (OMR)

- [Audiveris](https://github.com/Audiveris/audiveris), projeto da equipe
  Audiveris — reconhecimento óptico de partitura impressa e exportação
  MusicXML. Licença do projeto: [GNU AGPLv3](https://github.com/Audiveris/audiveris/blob/master/LICENSE).
  Maravi chama uma instalação local por linha de comando; não incorpora seu
  código-fonte, seu instalador nem seus modelos/dados ao repositório.
- [MuseScore Studio](https://github.com/musescore/MuseScore), equipe MuseScore —
  leitura do MusicXML compactado, conversão para MusicXML e MIDI e revisão
  humana da partitura. Licença do programa:
  [GNU GPLv3](https://github.com/musescore/MuseScore/blob/main/LICENSE.txt).
  Também é executado como programa externo instalado pelo usuário.
- [Poppler](https://poppler.freedesktop.org/) (`pdfinfo`, `pdfseparate`) e
  [ImageMagick](https://imagemagick.org/) (`identify`, `convert`) — verificação
  local de páginas/dimensões e preparação de cópias para o OMR. São ferramentas externas;
  consultar os avisos e licenças das versões instaladas ou incluídas numa
  futura distribuição.

O Maravi não redistribui essas ferramentas nesta fase. Se um pacote futuro
passar a incluí-las, será preciso inventariar versões, componentes internos,
fontes/modelos, avisos, licenças e obrigações de disponibilização do código
correspondente **antes** da distribuição. A invocação separada não é uma
garantia jurídica para todas as formas futuras de empacotamento.

## Auditoria da candidata Python/Linux — 23 out. 2026

O venv limpo Linux/Python 3.12 continha 44 distribuições Python do manifesto
e Basic Pitch. A candidata automatizada acrescentou os avisos de PyInstaller,
seus hooks e `altgraph`: o coletor em `packaging/build_linux.py` registrou
47 distribuições e 100 arquivos de aviso/licença, com cópias e
`INVENTORY.json` na saída `onedir`. É um inventário do venv, possivelmente
mais amplo que o conteúdo efetivamente incluído pelo congelamento. O arquivo
`NATIVE_BINARIES.json` lista 239 bibliotecas nativas regulares e 9 links
simbólicos presentes na candidata. `ABI_REPORT.json` registra os símbolos
glibc exigidos por arquivo (máximo observado 2.39 em `libmvec.so.1`);
isso não é validação em outras distribuições. A wheel de
`flatbuffers` 25.12.19 declara Apache 2.0 no metadata e nos cabeçalhos de
código, mas não contém um arquivo de licença separado; o aviso completo
precisa ser incorporado e conferido antes
da distribuição. Isso é inventário preliminar, não certificação jurídica.
A [licença no tag oficial v25.12.19](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE)
e o [script oficial de empacotamento Python](https://github.com/google/flatbuffers/blob/v25.12.19/python/setup.py)
confirmam a origem do texto; a ausência na wheel também foi
[reportada ao projeto](https://github.com/google/flatbuffers/issues/9170).

Merecem conferência individual antes de uma release: `soxr` (metadata
LGPL-2.1-or-later), `llvmlite` (BSD-2-Clause/Apache-2.0 com exceção LLVM),
`numpy` e `scipy` (múltiplos avisos para código e bibliotecas embutidas),
`soundfile`/libsndfile, `onnxruntime` e o bootloader do PyInstaller.
Alguns metadata têm campo de licença genérico, vazio ou não padronizado;
os arquivos de aviso são fonte mais precisa para auditoria, mas a presença
de arquivos não prova por si só cumprimento de todas as obrigações.
O modelo ONNX do Basic Pitch deve permanecer associado à sua proveniência
e licença. TensorFlow, embora declarado pelo pacote Basic Pitch, não está
instalado nesta combinação ONNX; `pip check` o reporta como ausente.

O reconhecimento automático é um rascunho, não uma transcrição autorizada ou
musicalmente revisada. A autoria da obra, da edição e da transcrição de origem
deve ser preservada. Só processe material para o qual tenha direito de uso.
Maravi não implementa upload da partitura a um serviço externo: chama o
executável local. Isso não é uma auditoria das conexões de rede feitas pelo
Audiveris, que, quando instalado à parte, pode oferecer o download de dados
de idioma para OCR.

Fontes para a integração: [manual do Audiveris](https://audiveris.github.io/audiveris/_pages/handbook/),
[interface de linha de comando](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/)
e [instalação de binários](https://audiveris.github.io/audiveris/_pages/tutorials/install/binaries/).

## Ensaio local de componentes tímbricos

O experimento `tools/explore_timbre_components.py` usa
[librosa](https://librosa.org/doc/main/api/generated/librosa.decompose.hpss.html)
(HPSS, licença [ISC](https://github.com/librosa/librosa/blob/main/LICENSE.md))
e [scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.NMF.html)
(NMF, licença [BSD-3-Clause](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING)).
É uma aplicação local dessas bibliotecas, sem copiar seus fontes nem incluir
modelos de terceiros. Nenhum componente resultante é identificado
automaticamente como flauta; o uso de uma gravação e dos derivados continua
sujeito aos direitos da obra e do fonograma.
