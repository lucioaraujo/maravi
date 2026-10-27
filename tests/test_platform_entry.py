"""Portable source entrypoint must remain loopback-only and without reloader."""

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

import run_maravi
from webapp.app import preview_process_command


class PlatformEntryTests(unittest.TestCase):
    def test_version_and_preview_command_for_frozen_app(self):
        with patch.object(run_maravi.sys, "argv", ["maravi", "--version"]), \
                patch("builtins.print") as printed:
            run_maravi.main()
        printed.assert_called_once_with("Maravi 0.1.0")
        source = Path("example.wav")
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(preview_process_command(source, "left"),
                             [sys.executable, "--analyze-preview", "example.wav", "--channel", "left"])

    def test_port_validation(self):
        self.assertEqual(run_maravi.local_port("5001"), 5001)
        for value in ("0", "1023", "65536", "not-a-port"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_maravi.local_port(value)

    def test_local_server_never_enables_reloader(self):
        with patch.object(run_maravi.sys, "argv", ["maravi"]), \
                patch.dict("run_maravi.os.environ", {"MARAVI_PORT": "5056", "MARAVI_NO_BROWSER": "1"}), \
                patch("webapp.app.app.run") as run, \
                patch("run_maravi.threading.Timer") as timer:
            run_maravi.main()
        run.assert_called_once_with(host="127.0.0.1", port=5056,
                                    debug=False, use_reloader=False)
        timer.assert_not_called()

    def test_browser_opens_the_local_page_unless_disabled(self):
        environ = {k: v for k, v in run_maravi.os.environ.items() if k != "MARAVI_NO_BROWSER"}
        environ["MARAVI_PORT"] = "5057"
        with patch.object(run_maravi.sys, "argv", ["maravi"]), \
                patch.dict("run_maravi.os.environ", environ, clear=True), \
                patch("webapp.app.app.run"), \
                patch("run_maravi.threading.Timer") as timer:
            run_maravi.main()
        timer.assert_called_once()
        self.assertEqual(timer.call_args.kwargs["args"], ("http://127.0.0.1:5057/",))


if __name__ == "__main__":
    unittest.main()
