"""Every supported SRS diagram has a notation guard and a real SVG render test."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import mermaid  # noqa: E402


DIAGRAMS = {
    "activity": '''flowchart TD
start((●)) --> validate(Validate order)
validate --> stop((◉))
''',
    "bpmn": '''flowchart LR
subgraph Pool["Order process"]
  start((Start)) --> task(Create order) --> finish(((End)))
end
''',
    "class_object": '''classDiagram
class Order {
  + id: UUID
}
''',
    "component": '''flowchart TB
subgraph Presentation
  ui["<<component>> Order UI"]
end
subgraph Application_Domain
  service["<<component>> Order Service"]
end
ui -.->|uses| service
''',
    "deployment": '''flowchart TB
client["<<device>> Client"] -->|HTTPS| host["<<execution environment>> App host"]
artifact["<<artifact>> order-app"]
host --> artifact
''',
    "dfd": '''flowchart LR
customer[Customer] -->|order details| validate((1. Validate order))
validate -->|validated order| orders[(Order table)]
orders -->|order record| notify((2. Notify customer))
notify -->|confirmation| customer
''',
    "erd": '''erDiagram
CUSTOMER {
  string id PK
}
ORDER {
  string id PK
  string customer_id FK
}
CUSTOMER ||--o{ ORDER : "places"
''',
    "sequence": '''sequenceDiagram
actor Customer
participant API
Customer->>+API: submit order
API-->>-Customer: order id
''',
    "state_machine": '''stateDiagram-v2
[*] --> Open
Open --> Closed : close
Closed --> [*]
''',
    "system_context": '''flowchart TB
admin(["Admin"]) -->|manages orders| sys[["Order service"]]
sys -->|stores orders| db[(Database)]
''',
    "use_case": '''flowchart LR
actor[/"Customer"/]
subgraph System["Order service"]
  order(["Place order"])
end
actor --- order
''',
}


class AllDiagramNotationTests(unittest.TestCase):
    def test_every_supported_kind_passes_its_notation_guard(self):
        for kind, source in DIAGRAMS.items():
            with self.subTest(kind=kind):
                self.assertEqual(mermaid.problems(kind, source), [])

    @unittest.skipUnless(mermaid.available(), "Mermaid CLI is not installed")
    def test_every_supported_kind_renders_to_svg(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            for kind, source in DIAGRAMS.items():
                with self.subTest(kind=kind):
                    svg = output / f"{kind}.svg"
                    rendered, why = mermaid.render(source, svg)
                    self.assertTrue(rendered, why)
                    self.assertIn("<svg", svg.read_text(encoding="utf-8"))

    def test_notation_guards_reject_a_wrong_defining_shape(self):
        cases = {
            "activity": "flowchart TD\na(Task) --> b(Other)",
            "bpmn": "flowchart LR\na(Task)",
            "component": "flowchart TB\na[Service]",
            "deployment": "flowchart TB\na[Server] --> b[App]",
            "dfd": "flowchart LR\na[Customer] --> b[Store]",
            "erd": "erDiagram\nORDER { string id PK }\nCUSTOMER { string id PK }\nORDER -- CUSTOMER",
            "sequence": "sequenceDiagram\nparticipant API",
            "state_machine": "stateDiagram-v2\nOpen --> Closed",
            "system_context": "flowchart TB\na[User] --> b[System]",
            "use_case": "flowchart LR\na[User] --> b[Goal]",
        }
        for kind, source in cases.items():
            with self.subTest(kind=kind):
                self.assertTrue(mermaid.problems(kind, source))


if __name__ == "__main__":
    unittest.main()
