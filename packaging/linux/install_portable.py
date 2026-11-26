# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install/remove Maravi under a user-owned prefix without touching user jobs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

APP = "maravi"
RECEIPT = "share/maravi-install/receipt.json"
MAX_FILES = 10000
MAX_BYTES = 1024**3


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_path(name):
    if not name or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("unsafe package path: " + name)
    if any(c in name for c in "\n\r\t\\\0"):
        raise ValueError("unsupported package path")
    return PurePosixPath(name)


def reject_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("symlink path refused: " + str(part))


def verify_package(package):
    manifest = package / "SHA256SUMS"
    reject_symlinks(manifest)
    rows, total = {}, 0
    lines = manifest.read_text(encoding="ascii").splitlines()
    if not lines or len(lines) > MAX_FILES:
        raise ValueError("invalid Maravi package manifest")
    for line in lines:
        sha, separator, name = line.partition("  ")
        safe_path(name)
        if not separator or len(sha) != 64 or name in rows:
            raise ValueError("invalid checksum entry")
        path = package / name
        reject_symlinks(path)
        if not path.is_file():
            raise ValueError("missing package file: " + name)
        total += path.stat().st_size
        if total > MAX_BYTES or digest(path) != sha:
            raise ValueError("checksum or size limit failed: " + name)
        rows[name] = sha
    if "usr/bin/maravi" not in rows or not any(name.startswith("usr/lib/maravi/") for name in rows):
        raise ValueError("incomplete Maravi package")
    return rows


def atomic_write(path, data, mode):
    reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".maravi-install-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(tmp, mode)
        reject_symlinks(path)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_receipt(prefix):
    path = prefix / RECEIPT
    reject_symlinks(path)
    if not path.exists():
        return {}
    record = json.loads(path.read_text(encoding="utf-8"))
    files = record.get("files")
    if record.get("schema") != 1 or record.get("prefix") != str(prefix) or not isinstance(files, dict):
        raise ValueError("invalid Maravi installation receipt")
    if len(files) > MAX_FILES:
        raise ValueError("receipt exceeds the file limit")
    for name, checksum in files.items():
        safe_path(name)
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise ValueError("invalid receipt checksum")
    return files


def save_receipt(prefix, files):
    data = json.dumps({"schema": 1, "prefix": str(prefix), "files": files}, indent=2) + "\n"
    atomic_write(prefix / RECEIPT, data.encode("utf-8"), 0o600)


def install(package, prefix):
    package_files = verify_package(package)
    version = (package / "VERSION").read_text(encoding="ascii").strip()
    if not version or any(c not in "0123456789." for c in version):
        raise ValueError("invalid Maravi version")
    app_root = package / "usr/lib/maravi" / version
    reject_symlinks(app_root)
    folders = [p for p in app_root.iterdir() if p.is_dir()]
    if len(folders) != 1:
        raise ValueError("expected one frozen Maravi application directory")
    folder = folders[0].name
    target_root = prefix / "lib/maravi" / version
    reject_symlinks(target_root)
    if target_root.exists():
        raise ValueError("Maravi version already exists: " + str(target_root))
    old = load_receipt(prefix)
    if old:
        raise ValueError("a Maravi installation already exists in this prefix")

    target_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(folders[0], target_root / folder, symlinks=False)
    wrapper = prefix / "bin/maravi"
    wrapper_data = (
        '#!/bin/sh\nhere=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        f'exec "$here/../lib/maravi/{version}/{folder}/maravi" "$@"\n').encode()
    atomic_write(wrapper, wrapper_data, 0o755)
    icon_source = package / "usr/share/icons/hicolor/180x180/apps/maravi.png"
    reject_symlinks(icon_source)
    icon_target = prefix / "share/icons/hicolor/180x180/apps/maravi.png"
    atomic_write(icon_target, icon_source.read_bytes(), 0o644)
    desktop = (
        "[Desktop Entry]\nType=Application\nName=Maravi\n"
        "GenericName=Music transcription\nExec=" + str(wrapper) + "\n"
        "Icon=" + str(icon_target) + "\nTerminal=true\nCategories=AudioVideo;Audio;Music;\n").encode()
    desktop_target = prefix / "share/applications/maravi.desktop"
    atomic_write(desktop_target, desktop, 0o644)

    files = {}
    for path in sorted((target_root / folder).rglob("*")):
        reject_symlinks(path)
        if path.is_file():
            files[path.relative_to(prefix).as_posix()] = digest(path)
    files["bin/maravi"] = hashlib.sha256(wrapper_data).hexdigest()
    files[icon_target.relative_to(prefix).as_posix()] = digest(icon_target)
    files[desktop_target.relative_to(prefix).as_posix()] = digest(desktop_target)
    save_receipt(prefix, files)
    print("Installed Maravi in", prefix)


def remove(prefix):
    files = load_receipt(prefix)
    kept = {}
    for name, checksum in files.items():
        path = prefix / name
        reject_symlinks(path)
        if path.is_file() and digest(path) == checksum:
            path.unlink()
        elif path.exists():
            kept[name] = checksum
            print("Modified file preserved:", path)
    receipt = prefix / RECEIPT
    if kept:
        save_receipt(prefix, kept)
    elif receipt.exists():
        receipt.unlink()
    for parent in (prefix / "lib/maravi", prefix / "lib", prefix / "bin",
                   prefix / "share/applications", prefix / "share/icons/hicolor/180x180/apps",
                   prefix / "share/icons/hicolor/180x180", prefix / "share/icons/hicolor",
                   prefix / "share/icons", prefix / "share/maravi-install", prefix / "share"):
        try:
            parent.rmdir()
        except OSError:
            pass
    print("Removed registered Maravi files; temporary jobs and user data were left alone.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--prefix", default=os.environ.get("PREFIX", str(Path.home() / ".local")))
    args = parser.parse_args()
    try:
        prefix = Path(os.path.abspath(args.prefix))
        if prefix == Path("/") or any(c in str(prefix) for c in '\n\r\t"%`$\\'):
            raise ValueError("unsupported installation prefix")
        reject_symlinks(prefix)
        remove(prefix) if args.remove else install(Path(__file__).resolve().parent, prefix)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
