#!/usr/bin/env python3
"""As páginas de instalação do site do Maravi, geradas do INSTALL.md.

O INSTALL.md do repositório é a fonte única (quatro línguas); este script
o converte em instalacao.html, instalacao-en.html, instalacao-fr.html e
instalacao-es.html, com o mesmo cabeçalho (faixa RASGO, menu, línguas) e
rodapé das páginas Sobre, lidos delas. Os .html gerados são derivados:
editar o INSTALL.md ou as páginas Sobre, nunca as instalacao*.html.

Uso:  python3 gerar_instalacao.py   (aplica também o seo.py; 2026-10-27)
"""

import html
import pathlib
import re

AQUI = pathlib.Path(__file__).parent
INSTALL = AQUI.parent / "INSTALL.md"
BLOB = "https://github.com/lucioaraujo/maravi/blob/main/"

# língua: (página Sobre, página de instalação, título do INSTALL.md, <title>, descrição)
PAGINAS = {
    "en": ("en.html", "instalacao-en.html", None, "Install Maravi — Linux",
           "How to install Maravi 0.1.0 on Linux: requirements, FFmpeg, the package, the optional tools to read printed scores, and where your files go."),
    "pt-BR": ("index.html", "instalacao.html", "## Português", "Instalar o Maravi — Linux",
              "Como instalar o Maravi 0.1.0 no Linux: requisitos, FFmpeg, o pacote, as ferramentas opcionais para ler partituras impressas e onde ficam os seus arquivos."),
    "fr": ("fr.html", "instalacao-fr.html", "## Français", "Installer Maravi — Linux",
           "Comment installer Maravi 0.1.0 sous Linux : configuration requise, FFmpeg, le paquet, les outils facultatifs pour lire les partitions imprimées et où vont vos fichiers."),
    "es": ("es.html", "instalacao-es.html", "## Español", "Instalar Maravi — Linux",
           "Cómo instalar Maravi 0.1.0 en Linux: requisitos, FFmpeg, el paquete, las herramientas opcionales para leer partituras impresas y dónde quedan sus archivos."),
}
TITULO = {"en": "Installing Maravi", "pt-BR": "Instalar o Maravi", "fr": "Installer Maravi", "es": "Instalar Maravi"}


def secao(texto, lang):
    """O trecho do INSTALL.md de uma língua (o inglês vai até o primeiro ---)."""
    partes = texto.split("\n---\n")
    if lang == "en":
        corpo = partes[0].split("\n", 3)[3]  # sem o título e a linha das línguas
        return corpo
    marca = PAGINAS[lang][2]
    for parte in partes[1:]:
        if parte.strip().startswith(marca):
            return parte.strip()[len(marca):]
    raise SystemExit("INSTALL.md: falta a seção " + marca)


def link(destino, lang):
    if destino.startswith(("http://", "https://")):
        return destino
    if destino.startswith("#from-source") or destino.startswith("INSTALL.md#from-source"):
        return PAGINAS["en"][1] + "#from-source"
    if destino.startswith("INSTALL.md#"):
        return PAGINAS[lang][1]
    return BLOB + destino


def inline(texto, lang):
    partes = re.split(r"(`[^`]+`)", texto)
    saida = []
    for parte in partes:
        if parte.startswith("`") and parte.endswith("`") and len(parte) > 1:
            saida.append("<code>%s</code>" % html.escape(parte[1:-1]))
            continue
        t = html.escape(parte, quote=False)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   lambda m: '<a href="%s">%s</a>' % (html.escape(link(html.unescape(m.group(2)), lang)), m.group(1)), t)
        saida.append(t)
    return "".join(saida)


def ancora(titulo):
    return re.sub(r"[^a-z0-9]+", "-", titulo.lower()).strip("-")


def markdown(texto, lang):
    """O subconjunto do INSTALL.md: títulos, parágrafos, listas, código."""
    linhas = texto.strip("\n").split("\n")
    out, i = [], 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip():
            i += 1
            continue
        if linha.startswith("```"):
            fim = i + 1
            while not linhas[fim].startswith("```"):
                fim += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(linhas[i + 1:fim])))
            i = fim + 1
            continue
        m = re.match(r"(#{2,3}) (.+)", linha)
        if m:
            nivel = len(m.group(1))
            out.append('<h%d id="%s">%s</h%d>' % (nivel, ancora(m.group(2)), inline(m.group(2), lang), nivel))
            i += 1
            continue
        if re.match(r"(\d+\.|-) ", linha):
            ordenada = linha[0].isdigit()
            itens = []
            while i < len(linhas) and (re.match(r"(\d+\.|-) ", linhas[i]) or linhas[i].startswith("   ")):
                if re.match(r"(\d+\.|-) ", linhas[i]):
                    itens.append([re.sub(r"^(\d+\.|-) ", "", linhas[i]), []])
                elif linhas[i].strip().startswith("- "):
                    itens[-1][1].append(linhas[i].strip()[2:])
                elif itens[-1][1]:
                    itens[-1][1][-1] += " " + linhas[i].strip()
                else:
                    itens[-1][0] += " " + linhas[i].strip()
                i += 1
            tag = "ol" if ordenada else "ul"
            corpo = []
            for texto_item, sub in itens:
                interno = "".join("<li>%s</li>" % inline(s, lang) for s in sub)
                corpo.append("<li>%s%s</li>" % (inline(texto_item, lang), "<ul>%s</ul>" % interno if sub else ""))
            out.append("<%s>%s</%s>" % (tag, "".join(corpo), tag))
            continue
        paragrafo = []
        while i < len(linhas) and linhas[i].strip() and not re.match(r"(#{2,3} |```|(\d+\.|-) )", linhas[i]):
            paragrafo.append(linhas[i].strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(paragrafo), lang))
    return "\n".join(out)


def moldura(sobre, instalacao):
    """Cabeçalho e rodapé da página Sobre, com os links apontando para ela."""
    texto = (AQUI / sobre).read_text(encoding="utf-8")
    cabeca = texto[texto.index("<body>") + len("<body>"):texto.index("<main")]
    cabeca = re.sub(r'href="#(?!conteudo)', 'href="%s#' % sobre, cabeca)
    for _, (s, inst, *_resto) in PAGINAS.items():
        cabeca = cabeca.replace('href="%s"' % s, 'href="%s"' % inst)
    rodape = texto[texto.index("</main>") + len("</main>"):texto.index("</body>")]
    rodape = re.sub(r'href="#', 'href="%s#' % sobre, rodape)
    return cabeca, rodape


def main():
    fonte = INSTALL.read_text(encoding="utf-8")
    for lang, (sobre, arquivo, _marca, titulo, descricao) in PAGINAS.items():
        cabeca, rodape = moldura(sobre, arquivo)
        pagina = """<!doctype html>
<html lang="%s">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="%s">
  <title>%s</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>%s<main id="conteudo" class="doc">
<h1>%s</h1>
%s
</main>%s</body>
</html>
""" % (lang, html.escape(descricao), html.escape(titulo), cabeca, TITULO[lang], markdown(secao(fonte, lang), lang), rodape)
        (AQUI / arquivo).write_text(pagina, encoding="utf-8")
    print("gerar_instalacao.py: %d páginas" % len(PAGINAS))
    import seo  # os metadados de todas as páginas, na mesma passada
    seo.main()


if __name__ == "__main__":
    main()
