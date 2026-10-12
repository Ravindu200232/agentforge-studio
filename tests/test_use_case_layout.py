"""Use-case actors that join the same goals are drawn apart, never on top of each other."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import mermaid  # noqa: E402

SHARED_GOALS = '''flowchart LR
subgraph Shop["Online shop"]
  browse(["Browse products"])
  order(["Place order"])
  track(["Track order"])
end
buyer[/"Buyer"/]
owner[/"Store owner"/]
admin[/"Admin"/]
gateway[/"Payment gateway"/]
buyer --- browse
buyer --- order
owner --- browse
owner --- order
admin --- browse
admin --- order
gateway --- order
'''


def _heads(svg: str) -> list[tuple[float, float]]:
    """The centre of every stick figure's head (r=10 circles)."""
    return [(float(x), float(y)) for x, y in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="10"', svg)]


class SpreadTests(unittest.TestCase):
    def test_far_apart_positions_are_kept(self):
        self.assertEqual(mermaid._spread([100.0, 400.0], 0, 1000, 150), [100.0, 400.0])

    def test_equal_wishes_are_centred_apart(self):
        self.assertEqual(mermaid._spread([300.0, 300.0], 0, 1000, 150), [225.0, 375.0])

    def test_bounds_are_respected(self):
        ys = mermaid._spread([40.0, 40.0, 40.0], 100, 1000, 150)
        self.assertEqual(sorted(ys), [100.0, 250.0, 400.0])
        ys = mermaid._spread([990.0, 990.0], 0, 1000, 150)
        self.assertEqual(sorted(ys), [850.0, 1000.0])

    def test_order_follows_the_wishes(self):
        ys = mermaid._spread([500.0, 480.0, 520.0], 0, 2000, 150)
        self.assertLess(ys[1], ys[0])
        self.assertLess(ys[0], ys[2])


class UseCaseLayoutTests(unittest.TestCase):
    def test_actors_in_one_column_have_a_full_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "use-case.svg"
            self.assertTrue(mermaid._render_use_case_svg(SHARED_GOALS, out))
            svg = out.read_text(encoding="utf-8")
        heads = _heads(svg)
        self.assertEqual(len(heads), 4)
        height = float(re.search(r'<svg[^>]* height="([\d.]+)"', svg).group(1))
        columns: dict[float, list[float]] = {}
        for x, y in heads:
            columns.setdefault(x, []).append(y)
            self.assertGreater(y, 0)
            self.assertLess(y + 90, height)         # the figure and its name stay on the canvas
        for ys in columns.values():
            ys.sort()
            for upper, lower in zip(ys, ys[1:]):
                self.assertGreaterEqual(lower - upper, mermaid._UC_ACTOR_GAP - 0.01)


if __name__ == "__main__":
    unittest.main()
