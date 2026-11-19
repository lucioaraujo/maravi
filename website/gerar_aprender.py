#!/usr/bin/env python3
"""As páginas Aprender do site do Maravi, lidas da ajuda do próprio app.

Nivelamento dos sites da família RASGO (autor, 19/11/2026: "nivele pelos
mais completos"). O app tem a página "Como usar o Maravi" (rota de ajuda),
com cada parte da tela explicada nas quatro línguas, em webapp/i18n.py
(chaves help_*). O site lê esse mesmo texto, para a janela e o site dizerem
a mesma coisa. Cabeçalho e rodapé vêm das páginas Sobre, como na
instalação (gerar_instalacao.py).

Uso:  python3 gerar_paginas.py && python3 gerar_aprender.py && python3 gerar_instalacao.py
"""

import html
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).parent
sys.path.insert(0, str(AQUI.parent / "webapp"))
import i18n  # noqa: E402  (TEXT: chave -> (pt, en, fr, es))

ORDEM = {"pt-BR": 0, "en": 1, "fr": 2, "es": 3}
# língua: (página Sobre, página Aprender, <title>, descrição)
PAGINAS = {
    "pt-BR": ("index.html", "aprender.html", "Aprender o Maravi",
              "Cada parte da tela do Maravi e o que ela faz: o áudio, a escrita, as pistas de andamento e tom, o processamento, a partitura, a revisão e a privacidade."),
    "en": ("en.html", "aprender-en.html", "Learn Maravi",
           "Every part of Maravi's screen and what it does: the audio, the notation, tempo and key cues, processing, the score, review and privacy."),
    "fr": ("fr.html", "aprender-fr.html", "Apprendre Maravi",
           "Chaque partie de l'écran de Maravi et ce qu'elle fait : l'audio, l'écriture, les repères de tempo et de tonalité, le traitement, la partition, la révision et la confidentialité."),
    "es": ("es.html", "aprender-es.html", "Aprender Maravi",
           "Cada parte de la pantalla de Maravi y lo que hace: el audio, la notación, las pistas de tempo y tono, el procesamiento, la partitura, la revisión y la privacidad."),
}
SECOES = ("audio", "instrument", "cues", "process", "score", "review", "privacy")


def t(chave, lang):
    return i18n.TEXT[chave][ORDEM[lang]]


def corpo(texto):
    out = []
    for par in [p for p in texto.split("\n\n") if p.strip()]:
        out.append("<p>%s</p>" % html.escape(" ".join(par.split()), quote=False))
    return "\n".join(out)


def moldura(sobre):
    texto = (AQUI / sobre).read_text(encoding="utf-8")
    inicio = re.search(r"<body[^>]*>", texto).end()
    cabeca = texto[inicio:texto.index("<main")]
    cabeca = re.sub(r'href="#(?!conteudo)', 'href="%s#' % sobre, cabeca)
    for s, apr, *_ in PAGINAS.values():   # o seletor de língua leva ao Aprender da outra língua
        cabeca = cabeca.replace('href="%s"' % s, 'href="%s"' % apr)
    rodape = texto[texto.index("</main>") + len("</main>"):texto.index("</body>")]
    rodape = re.sub(r'href="#', 'href="%s#' % sobre, rodape)
    return cabeca, rodape


def main():
    for lang, (sobre, arquivo, titulo, descricao) in PAGINAS.items():
        cabeca, rodape = moldura(sobre)
        partes = ["<h1>%s</h1>" % html.escape(t("help_title", lang), quote=False),
                  corpo(t("help_intro", lang))]
        for s in SECOES:
            partes.append('<h2 id="%s">%s</h2>' % (s, html.escape(t("help_%s_title" % s, lang), quote=False)))
            partes.append(corpo(t("help_%s_body" % s, lang)))
        pagina = """<!doctype html>
<html lang="%s">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="%s">
  <title>%s</title>
  <link rel="icon" href="assets/identity/maravi-favicon.svg" type="image/svg+xml">
  <link rel="icon" href="assets/identity/favicon-32.png" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="assets/identity/apple-touch-icon.png">
  <link rel="stylesheet" href="styles.css">
</head>
<body class="score-workspace">%s<main id="conteudo" class="doc">
%s
</main>%s</body>
</html>
""" % (lang, html.escape(descricao), html.escape(titulo), cabeca, "\n".join(partes), rodape)
        (AQUI / arquivo).write_text(pagina, encoding="utf-8")
    print("gerar_aprender.py: %d páginas" % len(PAGINAS))


if __name__ == "__main__":
    main()
