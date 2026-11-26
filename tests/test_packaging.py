"""Valida a receita local sem executar PyInstaller nem fazer rede."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "build_linux.py"
SPEC = importlib.util.spec_from_file_location("maravi_build_linux", BUILD_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
build_linux = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_linux)

FORMATS_SCRIPT = Path(__file__).resolve().parents[1] / "packaging" / "package_formats.py"
FORMATS_SPEC = importlib.util.spec_from_file_location("maravi_package_formats", FORMATS_SCRIPT)
assert FORMATS_SPEC is not None and FORMATS_SPEC.loader is not None
package_formats = importlib.util.module_from_spec(FORMATS_SPEC)
FORMATS_SPEC.loader.exec_module(package_formats)


class PackagingTests(unittest.TestCase):
    def test_frozen_relative_symlink_is_confined_to_payload(self):
        with tempfile.TemporaryDirectory(prefix="maravi-symlink-") as folder:
            root = Path(folder) / "payload"
            libraries = root / "numpy.libs"
            libraries.mkdir(parents=True)
            (libraries / "libopenblas.so").write_bytes(b"elf")
            (root / "libopenblas.so").symlink_to("numpy.libs/libopenblas.so")
            package_formats.validate_frozen_symlinks(root)

    def test_frozen_external_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="maravi-symlink-") as folder:
            base = Path(folder)
            root = base / "payload"
            root.mkdir()
            (base / "outside.so").write_bytes(b"elf")
            (root / "outside.so").symlink_to("../outside.so")
            with self.assertRaises(SystemExit):
                package_formats.validate_frozen_symlinks(root)

    def test_manifest_includes_application_and_bootloader(self):
        names = build_linux.package_names()
        self.assertIn("basic-pitch", names)
        self.assertIn("pyinstaller", names)
        self.assertEqual(len(names), len(set(names)))

    def test_native_inventory_only_lists_shared_libraries(self):
        with tempfile.TemporaryDirectory(prefix="maravi-native-inventory-") as folder:
            output = Path(folder)
            internal = output / "_internal"
            internal.mkdir()
            notices = output / "THIRD_PARTY_NOTICES"
            notices.mkdir()
            (internal / "engine.so").write_bytes(b"elf")
            (internal / "native.so.1").write_bytes(b"elf2")
            (internal / "not-a-library.txt").write_bytes(b"text")
            build_linux.write_native_inventory(output)
            rows = json.loads((notices / "NATIVE_BINARIES.json").read_text())
            self.assertEqual([row["path"] for row in rows],
                             ["_internal/engine.so", "_internal/native.so.1"])
            self.assertEqual([row["bytes"] for row in rows], [3, 4])
            self.assertTrue(all(row["symlink_target"] is None for row in rows))

    def test_launcher_and_archive(self):
        with tempfile.TemporaryDirectory(prefix="maravi-archive-") as folder:
            output = Path(folder) / "Maravi-9.9.9-linux-x86_64"
            output.mkdir()
            (output / "Maravi-9.9.9-linux-x86_64").write_bytes(b"elf")
            build_linux.write_launcher(output, "Maravi-9.9.9-linux-x86_64", "9.9.9")
            launcher = output / "maravi"
            self.assertTrue(launcher.stat().st_mode & 0o111)
            self.assertIn('"$here/Maravi-9.9.9-linux-x86_64"', launcher.read_text())
            self.assertIn("v9.9.9/INSTALL.md", (output / "README.txt").read_text())
            archive = build_linux.write_archive(output, Path(folder) / "out", "9.9.9")
            self.assertEqual(archive.name, "maravi-9.9.9-linux-x86_64.tar.xz")
            import tarfile
            with tarfile.open(archive) as tar:
                names = tar.getnames()
            self.assertIn("maravi-9.9.9-linux-x86_64/maravi", names)
            digest = (archive.parent / (archive.name + ".sha256")).read_text()
            self.assertTrue(digest.endswith("  maravi-9.9.9-linux-x86_64.tar.xz\n"))
            with self.assertRaises(SystemExit):
                build_linux.write_archive(output, Path(folder) / "out", "9.9.9")


if __name__ == "__main__":
    unittest.main()
