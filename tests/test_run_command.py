"""`tool_run_command`'s output decoding.

Found live: a real Windows build's `npm run build` output came back to the
chat as mojibake ("â–²" for "▲", "Æ’" for "ƒ", "âœ“" for "✓") - textbook UTF-8
bytes decoded with the wrong codec. `subprocess.Popen(..., text=True)` with no
explicit `encoding=` decodes with `locale.getpreferredencoding(False)`, which
on a Windows console is commonly cp1252, not UTF-8 - while npm/Next.js/Node
all emit UTF-8 once piped (not a TTY, exactly this case).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal.tools import WorkspaceTools  # noqa: E402


class RunCommandEncodingTests(unittest.TestCase):
    def _tools(self, tmp_path):
        return WorkspaceTools(tmp_path, client=None, approve=lambda _q: True)

    def test_subprocess_is_opened_with_explicit_utf8(self):
        # The regression itself: relying on the platform locale default is
        # exactly what broke on Windows. Lock in the explicit encoding.
        import subprocess as subprocess_module

        tools = self._tools(Path("."))
        with patch.object(subprocess_module, "Popen") as popen:
            popen.return_value.poll.return_value = 0
            popen.return_value.wait.return_value = 0
            popen.return_value.stdout.readline.return_value = ""
            tools.tool_run_command("echo hi")
        self.assertEqual(popen.call_args.kwargs.get("encoding"), "utf-8")

    def test_utf8_multibyte_output_round_trips_correctly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            tools = self._tools(Path(folder))
            # Exactly the characters the live build's own output used: a
            # box-drawing arrow, a checkmark, a Next.js route marker glyph.
            emitter = Path(folder) / "emit.py"
            emitter.write_text(
                "import sys\n"
                "sys.stdout.buffer.write('▲ Next.js ✓ done ƒ Middleware'.encode('utf-8'))\n",
                encoding="utf-8")
            result = tools.tool_run_command(f'{sys.executable} {emitter.name}')
        self.assertIn("▲ Next.js ✓ done ƒ Middleware", result)
        # The mojibake this would have produced under cp1252, so a future
        # regression fails loudly on the actual wrong text, not just a miss.
        self.assertNotIn("â–²", result)
        self.assertNotIn("Æ’", result)


if __name__ == "__main__":
    unittest.main()
