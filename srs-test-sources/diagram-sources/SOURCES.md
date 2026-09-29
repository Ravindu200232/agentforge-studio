# Diagram notation source index

`catalog.json` is the machine-readable version used by diagram generation and
cloud review. This page makes each evidence source visible in the source folder.
No source image, example domain data, branding, or artwork is copied into this
repository; the diagrams use only the notation facts listed below.

| Diagram | Evidence sources | Applied notation evidence |
| --- | --- | --- |
| Activity | [Sparx Systems](https://sparxsystems.org/resources/tutorials/uml2/activity-diagram.html), [UML Diagrams](https://www.uml-diagrams.org/activity-diagrams-reference.html) | Initial/final nodes, action, decision/merge, fork/join. |
| BPMN | [OMG BPMN 2.0](https://www.omg.org/spec/BPMN/2.0/PDF/), [SAP BPMN guide](https://help.sap.com/docs/EAD_CLOUD/c50a2057f35a4731838910588f247f4a/c819c2b86e1b10148f21b7f958207590.html) | Events, tasks, gateways, pool/lane, sequence/message flow. |
| Class/Object | [Visual Paradigm](https://www.visual-paradigm.com/guide/uml-unified-modeling-language/uml-class-diagram-tutorial/), [Mermaid](https://mermaid.js.org/syntax/classDiagram) | Compartments, visibility, typed members, multiplicity, relation end symbols. |
| Component | [Visual Paradigm](https://online.visual-paradigm.com/diagrams/tutorials/component-diagram-tutorial/), [TU Delft](https://cese01.ewi.tudelft.nl/software-systems/part-2/tutorials/uml/component.html) | Component/interface/dependency notation. |
| Deployment | [Microsoft](https://support.microsoft.com/en-us/visio/create-a-uml-deployment-diagram), [Sparx Systems](https://sparxsystems.com/resources/tutorials/uml2/deployment-diagram.html) | Nodes, artifacts and communication paths. |
| DFD | [GOV.UK](https://www.gov.uk/government/publications/accessing-ukhsa-protected-data/approval-standards-and-guidelines-data-flow-diagram) | External entity, process, store and named data flow. |
| ERD | [Mermaid](https://mermaid.js.org/syntax/entityRelationshipDiagram) | Entity attributes, PK/FK, Crow's Foot cardinality. |
| Sequence | [Mermaid](https://mermaid.js.org/syntax/sequenceDiagram.html), [Sparx Systems](https://sparxsystems.org/resources/tutorials/uml2/sequence-diagram.html) | Lifelines, calls/returns, activation and fragments. |
| State Machine | [UML Diagrams](https://www.uml-diagrams.org/state-machine-diagrams.html) | Initial/final pseudostates and transitions. |
| System Context | [System context diagram overview](https://en.wikipedia.org/wiki/System_context_diagram) | Central system boundary and labelled external interactions. |
| Use Case | [Visual Paradigm](https://www.visual-paradigm.com/guide/uml-unified-modeling-language/what-is-use-case-diagram/), [Mermaid](https://mermaid.js.org/syntax/usecase.html) | Actor, goal, boundary, include and extend. |

The renderer’s supported Mermaid syntax remains the final implementation limit;
when a standard symbol is unavailable, the prompt uses the documented closest
non-deceptive Mermaid approximation.
