"""The class-diagram prompt is held to UML notation, then rendered by Mermaid."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import mermaid  # noqa: E402


VALID_CLASS_DIAGRAM = '''classDiagram
direction LR
class Order {
  + id: UUID
  + placedAt: DateTime
  + place(customer: Customer): Boolean
}
class OrderLine {
  + quantity: Integer
}
class Customer {
  + id: UUID
}
class BookingStatus {
  <<enumeration>>
  Unpaid
  Paid
}
class ExampleOrder["order-482 : Order"] {
  <<object>>
  placedAt = 2026-09-29
}
Order "1" *-- "1..*" OrderLine : contains
Customer "1" --> "0..*" Order : places
'''


class ClassDiagramStandardTests(unittest.TestCase):
    def test_accepts_a_typed_compartmented_uml_class_diagram(self):
        self.assertEqual(mermaid.problems("class_object", VALID_CLASS_DIAGRAM), [])

    def test_rejects_ambiguous_or_incomplete_uml_notation(self):
        source = '''classDiagram
class Order {
  id: UUID
}
Order "1" -- "many" OrderLine
'''
        problems = mermaid.problems("class_object", source)
        joined = " ".join(problems)
        self.assertIn("visibility", joined)
        self.assertIn("multiplicity", joined)
        self.assertIn("verb", joined)

    def test_rejects_one_sided_multiplicity_and_unlabeled_relation(self):
        source = '''classDiagram
class User {
  + id: UUID
}
class Session {
  + id: UUID
}
User "1" --> Session
'''
        problems = mermaid.problems("class_object", source)
        self.assertTrue(any("both ends" in problem for problem in problems))
        self.assertTrue(any("verb" in problem for problem in problems))

    @unittest.skipUnless(mermaid.available(), "Mermaid CLI is not installed")
    def test_the_reference_notation_really_renders_to_svg(self):
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder) / "class.svg"
            rendered, why = mermaid.render(VALID_CLASS_DIAGRAM, svg)
            self.assertTrue(rendered, why)
            self.assertIn("<svg", svg.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
