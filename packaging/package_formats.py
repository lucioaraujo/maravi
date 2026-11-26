"""Build .deb, AppImage and user-local .tar.gz from the frozen Maravi payload."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = "maravi"
ICON_SOURCE = ROOT / "website/assets/identity/apple-touch-icon.png"
RUNTIME_LICENSE = ROOT / "packaging/linux/appimage/runtime/LICENSE"
LINUXDEPLOY_SHA256 = "c20cd71e3a4e3b80c3483cef793cda3f4e990aca14014d23c544ca3ce1270b4d"
RUNTIME_SHA256 = "156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074"
LIMIT_BYTES = 1024**3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_frozen_symlinks(source: Path) -> None:
    """Allow PyInstaller's relative aliases only when their target stays in the payload."""
    root = source.resolve(strict=True)
    for path in source.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            target = path.resolve(strict=True)
        except OSError as error:
            raise SystemExit(f"Broken frozen-payload symlink: {path}") from error
        if not target.is_relative_to(root) or not target.is_file():
            raise SystemExit(f"Symlink target is outside the frozen payload: {path}")


def write_wrapper(path: Path, version: str, folder: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        f'exec "$here/../lib/maravi/{version}/{folder}/maravi" "$@"\n',
        encoding="utf-8")
    path.chmod(0o755)


def write_tree(source: Path, version: str, stage: Path) -> tuple[Path, str]:
    folder = source.name
    tree = stage / "usr"
    appdir = tree / "lib/maravi" / version / folder
    appdir.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        raise SystemExit("Frozen payload root cannot be a symlink.")
    validate_frozen_symlinks(source)
    total = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
    if total > LIMIT_BYTES:
        raise SystemExit("Frozen payload exceeds the 1 GiB packaging limit.")
    if shutil.disk_usage(stage).free < 3 * 1024**3:
        raise SystemExit("Less than 3 GiB free before creating Linux package formats.")
    shutil.copytree(source, appdir)
    wrapper = tree / "bin/maravi"
    write_wrapper(wrapper, version, folder)
    applications = tree / "share/applications/maravi.desktop"
    applications.parent.mkdir(parents=True, exist_ok=True)
    applications.write_text(
        "[Desktop Entry]\nType=Application\nName=Maravi\n"
        "GenericName=Music transcription\nComment=Local music listening and notation tool\n"
        "Exec=maravi\nIcon=maravi\nTerminal=true\nCategories=AudioVideo;Audio;Music;\n",
        encoding="utf-8")
    icon = tree / "share/icons/hicolor/180x180/apps/maravi.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ICON_SOURCE, icon)
    doc = tree / "share/doc/maravi"
    doc.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "CREDITS.md"):
        shutil.copy2(ROOT / name, doc / name)
    runtime_doc = doc / "appimage-runtime"
    runtime_doc.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUNTIME_LICENSE, runtime_doc / "LICENSE")
    return tree, folder


def manifest(tree: Path, package: Path) -> None:
    lines = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        if path.is_symlink():
            raise SystemExit("Symlink found in install tree: " + str(path))
        lines.append(f"{sha256(path)}  {path.relative_to(package).as_posix()}")
    (package / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deb(tree: Path, output: Path, version: str) -> Path:
    root = output / ".deb-root"
    root.mkdir()
    shutil.copytree(tree, root / "usr")
    control = root / "DEBIAN/control"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(
        "Package: maravi\n"
        f"Version: {version}\n"
        "Section: sound\nPriority: optional\nArchitecture: amd64\n"
        "Maintainer: Lúcio de Araújo <rasgo.instruments@gmail.com>\n"
        "Depends: libc6 (>= 2.35), libgcc-s1, libstdc++6, ffmpeg\n"
        "Description: local music listening, transcription and notation tool\n",
        encoding="utf-8")
    destination = output / f"maravi-{version}-linux-x86_64.deb"
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(destination)],
                   check=True, timeout=300)
    shutil.rmtree(root)
    return destination


def write_portable(tree: Path, output: Path, version: str, folder: str) -> Path:
    package = output / f"maravi-{version}-linux-x86_64"
    package.mkdir()
    shutil.copytree(tree, package / "usr")
    (package / "VERSION").write_text(version + "\n", encoding="ascii")
    shutil.copy2(ROOT / "packaging/linux/install.sh", package / "install.sh")
    (package / "install.sh").chmod(0o755)
    shutil.copy2(ROOT / "packaging/linux/install_portable.py", package / "install_portable.py")
    (package / "README.txt").write_text(
        f"Maravi {version} — Linux x86_64\n\n"
        "Install for this user, without root: ./install.sh\n"
        "Remove this installation: ./install.sh --remove\n"
        "FFmpeg is required. Audiveris, MuseScore, Poppler and ImageMagick are optional.\n"
        f"Step-by-step guide: https://github.com/lucioaraujo/maravi/blob/v{version}/INSTALL.md\n",
        encoding="utf-8")
    manifest(package / "usr", package)
    archive = output / f"maravi-{version}-linux-x86_64.tar.gz"
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        tar.add(package, arcname=package.name)
    return archive


def write_appimage(tree: Path, output: Path, version: str, folder: str,
                   linuxdeploy: Path, runtime: Path) -> Path:
    if sha256(linuxdeploy) != LINUXDEPLOY_SHA256 or sha256(runtime) != RUNTIME_SHA256:
        raise SystemExit("Pinned AppImage tool/runtime checksum mismatch.")
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"],
                   cwd=ROOT / "packaging/linux/appimage/runtime", check=True)
    appdir = output / ".AppDir"
    shutil.copytree(tree, appdir / "usr")
    app_run = appdir / "AppRun"
    app_run.write_text(
        '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'exec "$HERE/usr/bin/maravi" "$@"\n', encoding="utf-8")
    app_run.chmod(0o755)
    binary = appdir / "usr/lib/maravi" / version / folder / folder
    # PyInstaller's onedir executable is named after the onedir folder.
    if not binary.is_file():
        raise SystemExit("PyInstaller executable not found: " + str(binary))
    destination = output / f"maravi-{version}-linux-x86_64.AppImage"
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1", ARCH="x86_64",
               LDAI_OUTPUT=str(destination), LDAI_RUNTIME_FILE=str(runtime.resolve()))
    subprocess.run([str(linuxdeploy.resolve()), "--appdir", str(appdir),
                    "--executable", str(binary),
                    "--desktop-file", str(appdir / "usr/share/applications/maravi.desktop"),
                    "--icon-file", str(appdir / "usr/share/icons/hicolor/180x180/apps/maravi.png"),
                    "--custom-apprun", str(app_run), "--output", "appimage"],
                   cwd=output, env=env, check=True, timeout=420)
    appimage = output / destination.name
    if not appimage.is_file():
        raise SystemExit("linuxdeploy did not create " + str(appimage))
    appimage.chmod(0o755)
    shutil.rmtree(appdir)
    return appimage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--linuxdeploy", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    namespace: dict[str, str] = {}
    exec((ROOT / "webapp/version.py").read_text(encoding="utf-8"), namespace)
    version = namespace["VERSION"]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maravi-formats-", dir=output) as temp:
        stage = Path(temp)
        tree, folder = write_tree(source, version, stage)
        write_deb(tree, output, version)
        shutil.rmtree(output / ".deb-root", ignore_errors=True)
        write_portable(tree, output, version, folder)
        write_appimage(tree, output, version, folder, args.linuxdeploy, args.runtime)
        (output / "SHA256SUMS").write_text("", encoding="ascii")
        assets = [output / f"maravi-{version}-linux-x86_64.deb",
                  output / f"maravi-{version}-linux-x86_64.AppImage",
                  output / f"maravi-{version}-linux-x86_64.tar.gz"]
        (output / "SHA256SUMS").write_text(
            "".join(f"{sha256(path)}  {path.name}\n" for path in assets), encoding="ascii")
    print("Built Linux distribution formats:", *(p.name for p in assets), flush=True)


if __name__ == "__main__":
    main()
