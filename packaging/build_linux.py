"""Cria uma candidata Linux onedir, sempre em diretório local ignorado novo.

Uso (dentro do venv de build): python -B packaging/build_linux.py [--archive PASTA]
Com --archive, grava também maravi-<versão>-linux-x86_64.tar.gz e o SHA256
nessa pasta (a CI da release, 2026-10-27). Não publica nada. Requer
PyInstaller instalado.
"""

from __future__ import annotations

import importlib.metadata as metadata
import json
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import hashlib
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "webapp" / "version.py"
REQUIREMENTS = ROOT / "requirements-local-linux-py312.txt"


def package_names() -> list[str]:
    names = [line.split("==", 1)[0] for line in REQUIREMENTS.read_text().splitlines()
             if "==" in line and not line.lstrip().startswith("#")]
    # O bootloader PyInstaller também faz parte da distribuição congelada.
    # Hooks e altgraph são ferramentas de build: seus avisos ficam no inventário
    # para rastreabilidade, mesmo que o código deles não entre no runtime.
    return sorted(set(names + ["basic-pitch", "pyinstaller",
                               "pyinstaller-hooks-contrib", "altgraph"]), key=str.casefold)


def collect_notices(destination: Path) -> None:
    destination.mkdir(exist_ok=True)
    inventory = []
    missing = []
    for name in package_names():
        distribution = metadata.distribution(name)
        package_dir = destination / f"{distribution.metadata['Name']}-{distribution.version}"
        notices = []
        for path in distribution.files or ():
            if not any(word in path.name.lower() for word in ("license", "licence", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(path))
            if not source.is_file():
                continue
            # Relative paths from wheel metadata remain inside this package's folder.
            relative = Path(*path.parts)
            if ".." in relative.parts or relative.is_absolute():
                raise RuntimeError(f"Caminho inválido no metadata de {name}: {path}")
            target = package_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            notices.append(str(relative))
        if not notices:
            missing.append(name)
        inventory.append({
            "name": distribution.metadata["Name"],
            "version": distribution.version,
            "scope": "build-tool" if name in {"pyinstaller-hooks-contrib", "altgraph"}
                     else "application-or-bootloader",
            "license_metadata": " ".join((distribution.metadata.get("License-Expression")
                                              or distribution.metadata.get("License")
                                              or "não especificada").split())[:160],
            "notice_files": notices,
        })
    (destination / "INVENTORY.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "AUDIT_STATUS.txt").write_text(
        "Inventário automático dos avisos presentes nas wheels do venv de build.\n"
        "Não substitui revisão jurídica nem cobre binários internos ou ferramentas externas.\n"
        "Pacotes sem arquivo de licença/aviso localizado no metadata: "
        + (", ".join(missing) if missing else "nenhum") + "\n",
        encoding="utf-8",
    )


def write_native_inventory(output: Path) -> None:
    """Lista binários nativos; sua presença não equivale a licença auditada."""
    binaries = []
    for path in sorted((output / "_internal").rglob("*")):
        if path.is_file() and re.search(r"\.so(?:\.|$)", path.name):
            binaries.append({"path": str(path.relative_to(output)),
                             "bytes": path.stat().st_size,
                             "symlink_target": str(path.readlink()) if path.is_symlink() else None})
    (output / "THIRD_PARTY_NOTICES" / "NATIVE_BINARIES.json").write_text(
        json.dumps(binaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_abi_report(output: Path) -> str:
    """Registra versões de glibc exigidas; não promete compatibilidade geral."""
    readelf = shutil.which("readelf")
    if readelf is None:
        raise RuntimeError("readelf/binutils é necessário para auditar a candidata Linux.")
    binaries = json.loads((output / "THIRD_PARTY_NOTICES" / "NATIVE_BINARIES.json").read_text())
    targets = [output / f"Maravi-{_version()}-linux-x86_64"]
    targets.extend(output / row["path"] for row in binaries if row["symlink_target"] is None)
    rows = []
    highest = (0, 0)
    for path in targets:
        process = subprocess.run([readelf, "--version-info", str(path)],
                                 check=True, capture_output=True, text=True, timeout=10)
        versions = [(int(major), int(minor)) for major, minor
                    in re.findall(r"GLIBC_(\d+)\.(\d+)", process.stdout)]
        if not versions:
            continue
        version = max(versions)
        highest = max(highest, version)
        rows.append({"path": str(path.relative_to(output)),
                     "highest_glibc_symbol": f"{version[0]}.{version[1]}"})
    label = f"{highest[0]}.{highest[1]}" if highest != (0, 0) else "não detectada"
    report = {"highest_glibc_symbol": label, "scanned_elf_files": len(targets),
              "note": "Versão exigida por símbolos ELF; não é teste de instalação em outra distribuição.",
              "files": rows}
    (output / "THIRD_PARTY_NOTICES" / "ABI_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return label


LAUNCHER = """#!/bin/sh
# Maravi: abre o servidor local e o navegador em http://127.0.0.1:5001/
# (MARAVI_PORT muda a porta; MARAVI_NO_BROWSER=1 não abre o navegador)
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$here/{name}" "$@"
"""

PACKAGE_README = """Maravi {version} - Linux x86_64

Start:     ./maravi        (the browser opens at http://127.0.0.1:5001/)
Stop:      Ctrl+C in the terminal, or close the terminal window
Required:  FFmpeg (sudo apt install ffmpeg)
Optional:  Audiveris, MuseScore, Poppler and ImageMagick, only to read
           printed scores (PDF/image)

Step by step, in four languages:
https://github.com/lucioaraujo/maravi/blob/v{version}/INSTALL.md

Your files stay on this computer. Each job lives in a temporary folder that
the system may clear on restart: save or download your MusicXML and MIDI.

License: GNU AGPL-3.0-or-later (LICENSE). Third-party notices:
CREDITS.md and THIRD_PARTY_NOTICES/.
"""


def write_launcher(output: Path, name: str, version: str) -> None:
    """O atalho `maravi` e o LEIA-ME curto do pacote (2026-10-27)."""
    launcher = output / "maravi"
    launcher.write_text(LAUNCHER.format(name=name), encoding="utf-8")
    launcher.chmod(0o755)
    (output / "README.txt").write_text(PACKAGE_README.format(version=version), encoding="utf-8")


def write_archive(output: Path, destination: Path, version: str) -> Path:
    """O .tar.gz da release, com a pasta inteira, e o seu SHA256."""
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"maravi-{version}-linux-x86_64.tar.gz"
    if archive.exists():
        raise SystemExit(f"{archive} já existe: não sobrescrever.")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(output, arcname=f"maravi-{version}-linux-x86_64")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return archive


def _version() -> str:
    namespace: dict[str, str] = {}
    exec(VERSION_FILE.read_text(encoding="utf-8"), namespace)
    return namespace["VERSION"]


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Esta receita foi validada somente com Python 3.12 no Linux.")
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise SystemExit("Esta receita gera apenas candidata Linux x86_64.")
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit("Instale PyInstaller no venv de build antes de executar.") from exc
    if shutil.which("readelf") is None:
        raise SystemExit("Instale binutils/readelf antes do build Linux.")
    version = _version()
    name = f"Maravi-{version}-linux-x86_64"
    build_parent = ROOT / ".local-build"
    build_parent.mkdir(exist_ok=True)
    gib = 1024 ** 3
    if shutil.disk_usage("/").free < 5 * gib:
        raise SystemExit("Menos de 5 GiB livres em /: não iniciar build.")
    if shutil.disk_usage(build_parent).free < 2 * gib:
        raise SystemExit("Menos de 2 GiB livres no disco de trabalho.")
    build_root = Path(tempfile.mkdtemp(prefix="maravi-linux-build-", dir=build_parent))
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--log-level", "WARN", "--onedir", "--name", name,
        "--specpath", str(build_root), "--workpath", str(build_root / "build"),
        "--distpath", str(build_root / "dist"),
        "--paths", str(ROOT / "tools"), "--paths", str(ROOT / "webapp"),
        "--add-data", f"{ROOT / 'webapp/templates'}:webapp/templates",
        "--add-data", f"{ROOT / 'webapp/static'}:webapp/static",
        "--collect-data", "basic_pitch", str(ROOT / "run_maravi.py"),
    ]
    print(f"Build local: {build_root}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True, timeout=420)
    output = build_root / "dist" / name
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    shutil.copy2(ROOT / "CREDITS.md", output / "CREDITS.md")
    write_launcher(output, name, version)
    collect_notices(output / "THIRD_PARTY_NOTICES")
    write_native_inventory(output)
    abi = write_abi_report(output)
    if "--archive" in sys.argv[1:]:
        index = sys.argv.index("--archive")
        archive = write_archive(output, Path(sys.argv[index + 1]).resolve(), version)
        print(f"Arquivo: {archive}", flush=True)
    print(f"Candidata local (não publicar sem revisão): {output}", flush=True)
    print(f"Executável: {output / name}", flush=True)
    print(f"Maior símbolo de glibc exigido: {abi} (ver ABI_REPORT.json)", flush=True)


if __name__ == "__main__":
    main()
