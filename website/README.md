# Site do Maravi

**Estado (2026-10-27):** publicado com a v0.1.0 em
<https://lucioaraujo.github.io/maravi/> (GitHub Pages do repositório próprio;
`.github/workflows/deploy-site.yml`, que só roda quando o site muda).

## Páginas e como gerar

- `index.html` (português, canônica), `en.html`, `fr.html`, `es.html`: a
  página Sobre, **editada à mão** (a fonte; o texto editorial confirmado
  pelo autor em 22–23 out. 2026, com as mudanças da publicação).
- `instalacao*.html`: **derivadas** do `INSTALL.md` do repositório por
  `python3 gerar_instalacao.py`, que lê o cabeçalho e o rodapé das páginas
  Sobre e aplica o `seo.py`. Editar o `INSTALL.md`, nunca essas páginas.
- `seo.py`: os metadados (canonical, hreflang, Open Graph, JSON-LD) e o
  `sitemap.xml`; o código comum da família RASGO, copiado do Aquorbium; só a
  configuração do topo é do Maravi. A imagem de compartilhamento
  `assets/og-maravi.jpg` (1200×630) é uma captura do app.

Depois de editar uma página Sobre: `python3 gerar_instalacao.py` (refaz as
de instalação e os metadados). Os testes estão em `tests/test_website.py`.

## Regras da família

- A faixa fixa `rasgo-strip` aponta para o portal; o cabeçalho próprio vem
  logo abaixo.
- Fontes livres e embutidas, as mesmas do app (Fraunces, Work Sans,
  JetBrains Mono, SIL OFL 1.1, `assets/fonts/OFL.txt`); nenhuma fonte de
  sistema nomeada.
- O contato não usa `mailto`: o botão abre um diálogo, e
  `assets/contact.js` (cópia do Aquorbium, `b82d2d1`) monta o endereço.
- O download aponta para a release mais recente no GitHub.

## Histórico


Fonte local das quatro páginas: `index.html` (português), `en.html`,
`fr.html`, `es.html` e `styles.css`. Não são o aplicativo Flask nem um pacote
instalável. O desenho da pauta é somente ilustrativo, feito em CSS.

Identidade editorial confirmada pelo autor em 22–23 out. 2026: Maravi é um
dispositivo da família RASGO, parte da pesquisa, para estudo, escuta,
notação e apoio ao arquivo musical. Não é um instrumento musical. A página
não promete preservação durável dos jobs temporários; fontes e derivados
precisam de proveniência e gestão próprias. O tutorial distingue a escolha
manual do instrumento da pauta das sugestões automáticas de tempo e tom.
As quatro páginas têm seção de contato visível, com o endereço usado em
outros projetos RASGO: `rasgo.instruments@gmail.com`.

Decisão editorial de 22 out. 2026: GitHub deverá hospedar código e releases;
o portal RASGO apresentará o projeto e levará ao site/download quando houver
uma versão local testada. A primeira entrega processará arquivos no próprio
computador do usuário. Não conectar o formulário local do Maravi à internet,
nem anunciar uma URL de download inexistente.

Estas páginas são um rascunho para revisão do autor. Nenhuma foi enviada à
HostGator ou ao GitHub Pages; o portal RASGO atual não foi modificado. Antes
de publicar, decidir o repositório e URL definitivos, revisar as traduções,
conferir a instalação em outra máquina Linux, a escuta musical, as
dependências e as licenças;
então adicionar o card Maravi nas quatro páginas do portal, com link válido e
estado correto. Conferir o site próprio e o portal já no ar após cada envio.

Para ver a página localmente, abra `index.html` no navegador. Nenhum arquivo
de áudio ou partitura faz parte desta página estática.

Validação de 22 out. 2026: dois testes locais de idiomas, links, âncoras e
ausência de download fictício passaram; captura da página portuguesa em
1365 × 900 foi inspecionada sem sobreposição visível e com cinco linhas na
pauta ilustrativa. Não houve revisão visual em celular nem revisão humana
das três traduções. Os oito testes do pacote do portal existente também
passaram; esse portal não foi modificado.

Na atualização seguinte, o menu ganhou “Sobre” e a seção passou a distinguir
autoria do Maravi, licença do próprio código e créditos das ferramentas usadas
no áudio e no OMR. A página não anuncia disponibilidade multiplataforma:
o código-fonte ganhou uma entrada local comum e ajustes de descoberta de
ferramentas, mas Windows/macOS e pacotes continuam sem validação.

Validação técnica de 23 out. 2026: 78 testes Python locais passaram,
incluindo idioma, âncoras e endereço de contato. Não houve revisão visual
ou teste de envio de e-mail; nenhum site foi publicado nesta sessão.
Depois disso, o ambiente Linux/Python 3.12 foi reproduzido em venv limpo,
com 83 testes, áudio sintético, OMR simples e candidata local PyInstaller.
Isso não altera o estado editorial: não há release nem página pública Maravi.

Atualização de 23 out. 2026: as quatro páginas editoriais foram inspecionadas
em Chromium headless a 1440 px de largura. Navegação, pauta ilustrativa,
instruções, limites, créditos e avisos de estado estão visíveis sem
sobreposições na área capturada. A inspeção não substitui a revisão das
traduções por falantes nem a verificação no navegador/host público. A candidata
Linux passou no smoke test local, mas a página segue em pré-publicação até a
auditoria de distribuição e a revisão musical humana serem concluídas.
