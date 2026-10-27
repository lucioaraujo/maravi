#!/usr/bin/env python3
"""As páginas Sobre do site do Maravi, com o layout do aplicativo.

O autor, 2026-10-27: "cria o site com o mesmo layout do aplicativo". O
desenho segue a tela inicial do app (webapp/templates/index.html e a camada
score-workspace de webapp/static/style.css): o papel pautado, o cabeçalho
verde com a linha dourada, o painel de introdução com a pauta em SVG e o
painel do formulário com os cartões numerados.

Fontes dos textos, sem segunda cópia:
- os do app (título, pauta, legenda, o caminho em quatro passos) vêm de
  webapp/i18n.py, nas quatro línguas;
- os do site (como usar, pesquisa, sobre, créditos, contato) vêm de
  textos.json, o texto editorial confirmado pelo autor em 22-23 out. 2026
  com as mudanças da publicação. Editar ali.

Gera index.html (português), en.html, fr.html, es.html; os .html são
derivados. Depois, gerar_instalacao.py refaz as páginas de instalação (com
o mesmo cabeçalho) e os metadados (seo.py).

Uso:  python3 gerar_paginas.py && python3 gerar_instalacao.py
"""

import html
import json
import pathlib
import sys

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "webapp"))
import i18n  # noqa: E402  (os textos do aplicativo)

REPO = "https://github.com/lucioaraujo/maravi"
RELEASE = REPO + "/releases/latest"
LINGUAS = [("pt", "pt-BR", "index.html", "PT"), ("en", "en", "en.html", "EN"),
           ("fr", "fr", "fr.html", "FR"), ("es", "es", "es.html", "ES")]
INSTALACAO = {"pt": "instalacao.html", "en": "instalacao-en.html",
              "fr": "instalacao-fr.html", "es": "instalacao-es.html"}
# o que só o site diz (o resto vem do app ou do textos.json)
SITE = {
    "pt": {"badge": "Versão 0.1.0 · Linux", "dl_index": "Baixar · 01 / 02",
           "dl_title": "Baixar e instalar"},
    "en": {"badge": "Version 0.1.0 · Linux", "dl_index": "Download · 01 / 02",
           "dl_title": "Download and install"},
    "fr": {"badge": "Version 0.1.0 · Linux", "dl_index": "Télécharger · 01 / 02",
           "dl_title": "Télécharger et installer"},
    "es": {"badge": "Versión 0.1.0 · Linux", "dl_index": "Descargar · 01 / 02",
           "dl_title": "Descargar e instalar"},
}

e = lambda s: html.escape(s, quote=False)
a = lambda s: html.escape(s, quote=True)


def app(chave, lang):
    return i18n.TEXT[chave][i18n.LANGUAGES.index(lang)]


PAUTA = """<svg viewBox="0 0 720 210" role="img" aria-labelledby="notation-title notation-desc" xmlns="http://www.w3.org/2000/svg">
        <title id="notation-title">{titulo}</title>
        <desc id="notation-desc">{desc}</desc>
        <g class="staff-lines"><path d="M20 60H700 M20 75H700 M20 90H700 M20 105H700 M20 120H700"/></g>
        <g class="bar-lines"><path d="M448 60V120 M686 60V120 M694 60V120"/></g>
        <path class="clef-mark" d="M71 151C53 156 40 142 42 126C44 110 63 100 77 108C88 116 82 131 69 131C56 130 50 115 58 100C65 87 89 69 96 48C103 27 88 15 78 28C68 40 75 58 88 76C105 100 108 123 98 145C92 158 81 165 71 164"/>
        <g class="time-mark"><text x="118" y="89">4</text><text x="118" y="117">4</text></g>
        <g class="ledger-lines"><path d="M157 135H190 M616 135H648"/></g>
        <g class="note-stems"><path d="M181 135V92 M254 128V85 M319 120V73 M354 113V66 M413 105V64 M513 120V79 M574 128V85 M639 135V92"/></g>
        <path class="note-beam" d="M318 72L354 65L354 72L318 79Z"/>
        <g class="note-heads"><ellipse cx="172" cy="135" rx="12" ry="8" transform="rotate(-19 172 135)"/><ellipse cx="245" cy="128" rx="12" ry="8" transform="rotate(-19 245 128)"/><ellipse cx="310" cy="120" rx="12" ry="8" transform="rotate(-19 310 120)"/><ellipse cx="345" cy="113" rx="12" ry="8" transform="rotate(-19 345 113)"/><ellipse cx="404" cy="105" rx="12" ry="8" transform="rotate(-19 404 105)"/><ellipse class="half-note" cx="504" cy="120" rx="12" ry="8" transform="rotate(-19 504 120)"/><ellipse cx="565" cy="128" rx="12" ry="8" transform="rotate(-19 565 128)"/><ellipse cx="630" cy="135" rx="12" ry="8" transform="rotate(-19 630 135)"/></g>
        <path class="phrase-slur" d="M168 151C230 170 355 169 411 129"/>
        <circle class="articulation-dot" cx="404" cy="89" r="3"/>
        <path class="accent-mark" d="M552 109L577 115L552 121"/>
        <path class="crescendo-mark" d="M486 173L625 159 M486 173L625 187"/>
        <text class="dynamic-mark" x="169" y="190">p</text>
      </svg>"""


def pagina(lang, codigo, arquivo):
    t = json.load(open(AQUI / "textos.json", encoding="utf-8"))[lang]
    s = SITE[lang]
    ids = t["ids"]  # ideia, uso, pesquisa, sobre, contato (por língua)
    nav = "\n      ".join('<a href="%s">%s</a>' % (a(href if not href.startswith("#") else href), e(rotulo))
                          for href, rotulo in t["nav"] if not href.startswith("#" + ids[0]))
    langs = "".join('<a href="%s" lang="%s"%s>%s</a>' % (f, c, ' aria-current="page"' if l == lang else "", r)
                    for l, c, f, r in LINGUAS)
    cards = []
    for numero, ((indice, titulo, texto), (gtitulo, passos)) in enumerate(zip(t["cards"], t["guides"]), start=1):
        lista = "".join("<li>%s</li>" % p for p in passos)
        cards.append(f"""      <section class="form-card">
        <h3 class="legend"><span class="legend-number">0{numero}</span> {titulo}</h3>
        <p class="card-index">{indice.split("/")[-1].strip()}</p>
        <p>{texto}</p>
        <h4>{gtitulo}</h4>
        <ol>{lista}</ol>
      </section>""")
    creditos = "".join("<li>%s</li>" % c for c in t["creditos"])
    pesquisa = "".join("<p>%s</p>" % p for p in t["pesquisa"])
    d = t["dialog"]
    return f"""<!doctype html>
<html lang="{codigo}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{a(t["desc"])}">
  <title>{e(t["title"])}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body class="score-workspace">
<div class="rasgo-strip"><a href="{a(t["portal"][0])}">{t["strip"]}</a></div>
<a class="skip-link" href="#conteudo">{t["skip"]}</a>
<header class="site-header">
  <div class="site-header-inner">
    <a class="wordmark" href="{arquivo}#{ids[0]}" aria-label="Maravi">RASGO <span>/ MARAVI</span></a>
    <nav class="header-actions" aria-label="Maravi">
      <span class="local-badge"><span class="status-dot"></span> {e(s["badge"])}</span>
      {nav}
    </nav>
    <nav class="help-languages" aria-label="{a(t["lang_label"])}">{langs}</nav>
  </div>
</header>

<main id="conteudo">
<div class="workspace-layout" id="{ids[0]}">
  <aside class="intro-panel">
    <p class="eyebrow">{e(app("hero_kicker", lang))}</p>
    <h1>{e(app("hero_first", lang))}<br><em>{e(app("hero_second", lang))}</em></h1>
    <p class="intro-copy">{e(app("hero_copy", lang))}</p>
    <figure class="notation-example">
      {PAUTA.format(titulo=e(app("score_example_title", lang)), desc=e(app("score_example_desc", lang)))}
      <figcaption>{e(app("score_example_caption", lang))}</figcaption>
      <div class="notation-legend" aria-label="{a(app("score_legend", lang))}">
        <span><strong>4/4</strong> {e(app("legend_meter", lang))}</span>
        <span><strong>{e(app("legend_slur", lang))}</strong> {e(app("legend_slur_desc", lang))}</span>
        <span><strong>p</strong> {e(app("legend_soft", lang))}</span>
        <span><strong>&lt;</strong> {e(app("legend_crescendo", lang))}</span>
      </div>
    </figure>
  </aside>

  <section class="form-surface" id="{ids[1]}" aria-labelledby="baixar-titulo">
    <div class="form-heading">
      <span class="section-index">{t["eyebrows"][0]}</span>
      <h2 id="baixar-titulo">{e(s["dl_title"])}</h2>
      <p>{t["lead"]}</p>
      <p class="status">{t["status"]}</p>
      <div class="actions">
        <a class="button button-primary" href="{RELEASE}">{t["buttons"][0]}</a>
        <a class="button" href="{INSTALACAO[lang]}">{t["buttons"][1]}</a>
      </div>
    </div>
    <div class="form-cards">
      <p class="section-index">{t["eyebrows"][1]} · <span>{t["h2"][0]}</span></p>
{chr(10).join(cards)}
      <p class="hint">{t["uso_note"]}</p>
    </div>
  </section>

  <section class="process-panel" aria-label="{a(app("process_title", lang))}">
    <ol class="process-list">
      <li><span>01</span><p>{e(app("process_listening", lang))}</p></li>
      <li><span>02</span><p>{e(app("process_notation", lang))}</p></li>
      <li><span>03</span><p>{e(app("process_interpretation", lang))}</p></li>
      <li><span>04</span><p>{e(app("process_composition", lang))}</p></li>
    </ol>
    <p class="intro-footnote">{e(app("scope_note", lang))}</p>
  </section>
</div>

<section class="paper-section research" id="{ids[2]}">
  <p class="eyebrow">{t["eyebrows"][2]}</p>
  <h2>{t["h2"][1]}</h2>
  {pesquisa}
</section>

<section class="paper-section" id="{ids[3]}">
  <p class="eyebrow">{t["eyebrows"][3]}</p>
  <h2>{t["h2"][2]}</h2>
  <p>{t["sobre_p"]}</p>
  <h3>{t["creditos_h3"]}</h3>
  <ul class="credit-list">{creditos}</ul>
  <p class="hint">{t["creditos_note"]}</p>
</section>

<section class="paper-section" id="{ids[4]}">
  <p class="eyebrow">{t["eyebrows"][4]}</p>
  <h2>{t["h2"][3]}</h2>
  <p>{t["contato_p"]}</p>
  <div class="actions">
    <a class="button button-primary" href="#{ids[4]}" data-contact-trigger>{t["buttons"][2]}</a>
    <a class="button" href="{REPO}">{t["buttons"][3]}</a>
  </div>
</section>
</main>

<footer class="site-footer"><span>RASGO / MARAVI</span><span>{t["footer"]} · <a href="{REPO}">GitHub</a> · <a href="{REPO}/blob/main/LICENSE">{t["lic"]}</a> · <a href="{a(t["portal"][0])}">{t["portal"][1]}</a></span></footer>
<dialog class="contact-dialog" data-contact-dialog aria-labelledby="contact-title">
  <button class="dialog-close" type="button" data-contact-close aria-label="{d[3]}">×</button>
  <h2 id="contact-title">{d[0]}</h2>
  <p>{d[1]}</p>
  <code data-contact-address></code>
  <button class="button button-primary" type="button" data-contact-copy>{d[2]}</button>
  <p class="contact-feedback" data-contact-feedback data-copied="{d[4]}" data-fallback="{d[5]}" aria-live="polite"></p>
</dialog>
<script src="assets/contact.js" defer></script>
</body>
</html>
"""


def main():
    for lang, codigo, arquivo, _ in LINGUAS:
        (AQUI / arquivo).write_text(pagina(lang, codigo, arquivo), encoding="utf-8")
    print("gerar_paginas.py: %d páginas" % len(LINGUAS))


if __name__ == "__main__":
    main()
