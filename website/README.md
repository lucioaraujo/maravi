# Página editorial do Maravi — pré-publicação

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
