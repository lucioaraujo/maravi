"""Entrada local do Maravi para Linux, Windows e macOS (a partir do código-fonte).

Não é um instalador; as dependências devem estar disponíveis no Python usado.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser

from webapp.version import VERSION


def local_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("MARAVI_PORT deve ser um número entre 1024 e 65535.") from exc
    if not 1024 <= port <= 65535:
        raise ValueError("MARAVI_PORT deve estar entre 1024 e 65535.")
    return port


def main() -> None:
    if sys.argv[1:] == ["--version"]:
        print(f"Maravi {VERSION}")
        return
    if sys.argv[1:2] == ["--analyze-preview"]:
        # O binário congelado não é um interpretador Python. Ele executa a
        # mesma pré-análise em outro processo, preservando o timeout do webapp.
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from webapp import app as _app  # ativa os caminhos locais de módulos
        from analyze_audio_preview import main as preview_main

        preview_main()
        return
    if len(sys.argv) > 1:
        raise SystemExit("Uso: maravi [--version]")
    from webapp.app import app

    port = local_port(os.environ.get("MARAVI_PORT", "5001"))
    url = f"http://127.0.0.1:{port}/"
    print(f"Maravi {VERSION} — {url}", flush=True)
    # o navegador abre sozinho para quem não usa terminal (v0.1.0);
    # MARAVI_NO_BROWSER=1 desliga (testes, servidores sem tela)
    if not os.environ.get("MARAVI_NO_BROWSER"):
        opener = threading.Timer(1.2, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
