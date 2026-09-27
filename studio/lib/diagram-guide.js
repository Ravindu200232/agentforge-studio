// Fallback metadata reader guidance for legacy diagram revisions.
export const DIAGRAM_GUIDE = {
  use_case: {
    question: 'What is a Use Case Diagram?',
    definition: 'A UML use case diagram shows the system boundary, the external actors that use it, and the observable goals they expect it to fulfil.',
    businessSummary: 'An overview of what different people can do in this application, defining clear boundaries between customer actions and administrative tasks.',
    flowExplanation: [
      '1. A user visits the platform and is recognized by their role (e.g. Guest, Customer, or Manager).',
      '2. Based on their permissions, the user sees only the actions and buttons they are authorized to use.',
      '3. When the user takes an action (such as searching, booking, or modifying records), the system securely executes that goal.',
      '4. The platform confirms completion and updates the user interface instantly.'
    ],
    keyTakeaways: [
      'Clear role separation prevents unauthorized access to private data.',
      'Every action has an explicit business purpose and success confirmation.'
    ],
    drawingRules: [
      'Start with actors outside one named system boundary and actor goals inside it.',
      'Connect actors only to goals supported by approved roles and capabilities.',
      'Use include, extend, or generalization only when it is explicit in the SRS.',
    ],
  },
  sequence: {
    question: 'What is a Sequence Diagram?',
    definition: 'A UML sequence diagram shows how an actor and system participants exchange messages for one scenario, with time progressing from top to bottom.',
    businessSummary: 'A step-by-step chronological story showing what happens behind the scenes from the moment a user clicks a button until the database updates.',
    flowExplanation: [
      '1. The user fills out an on-screen form and clicks submit.',
      '2. The web browser validates the input and sends a secure request to the application server.',
      '3. The server checks the user session and permission before touching any data.',
      '4. The database executes the change atomically and responds with success.',
      '5. The user receives clear visual feedback confirming their action was saved.'
    ],
    keyTakeaways: [
      'No step can be bypassed: security verification happens on every single request.',
      'Data is saved before a success confirmation is shown to the user.'
    ],
    drawingRules: [
      'Start with the initiating actor, application participants, and lifelines.',
      'Draw requests in execution order and show their return messages.',
      'Use conditional, optional, loop, or parallel fragments only when specified.',
    ],
  },
  erd: {
    question: 'What is an Entity-Relationship Diagram?',
    definition: 'An ER diagram is a database blueprint showing persistent entities, attributes, keys, relationships, and supported cardinalities.',
    businessSummary: 'The memory blueprint of the software, showing all the collections and records the app saves and how they link together.',
    flowExplanation: [
      '1. Every primary business object (e.g. Users, Orders, Products) has its own structured database collection.',
      '2. Each record is assigned a unique identifier that guarantees it can never be confused with another record.',
      '3. Relationships link parent and child records (for example, each Booking points directly to the Customer who made it).',
      '4. When information is updated, related records stay accurate and organized without data duplication.'
    ],
    keyTakeaways: [
      'Strong relational links prevent lost or orphaned customer records.',
      'Field validation guarantees that corrupted or incomplete records cannot enter the database.'
    ],
    drawingRules: [
      'Start from approved entities and list typed primary- and foreign-key attributes.',
      'Connect only explicit relationships or resolvable foreign-key references.',
      'Show cardinality and optionality only when the schema supports them.',
    ],
  },
  activity: {
    question: 'What is an Activity Diagram?',
    definition: 'A UML activity diagram models a workflow as actions connected by control flow, including supported choices, loops, and concurrent work.',
    businessSummary: 'A flowchart tracing how a user moves through a complete process from start to finish, including choices and error checks.',
    flowExplanation: [
      '1. The process starts when the user enters the workflow.',
      '2. The system checks initial conditions (e.g. is the user signed in? is stock available?).',
      '3. If conditions are met, the main action proceeds smoothly along the happy path.',
      '4. If an issue occurs (e.g. missing field or payment decline), the system gracefully guides the user to correct it.',
      '5. The workflow ends in an approved, completed state.'
    ],
    keyTakeaways: [
      'Every branch has an explicit resolution so users never get stuck on a dead-end screen.',
      'Errors are caught early with helpful guidance rather than technical crash screens.'
    ],
    drawingRules: [
      'Start at one initial node, follow the ordered workflow, and finish at a final node.',
      'Use decision and merge nodes only for explicit guarded alternatives.',
      'Use fork and join bars only for explicitly parallel activities.',
    ],
  },
  class_object: {
    question: 'What is a Class & Object Diagram?',
    definition: 'A UML class diagram describes static types, attributes, operations, and relationships; an object view shows an illustrative runtime instance.',
    businessSummary: 'A map of the internal building blocks and data models that the code uses to manage business operations.',
    flowExplanation: [
      '1. Business models define what attributes each object possesses (e.g. price, status, date).',
      '2. Associated operations specify what actions can be performed on each object.',
      '3. Objects interact cleanly through defined interfaces to execute business logic.'
    ],
    keyTakeaways: [
      'Modular code objects make the system easier to test, maintain, and upgrade.'
    ],
    drawingRules: [
      'Start with one compartmented class box per supported domain type.',
      'List typed attributes and operations only when present in the SRS model.',
      'Add multiplicity, aggregation, composition, or inheritance only with evidence.',
    ],
  },
  state_machine: {
    question: 'What is a State Machine Diagram?',
    definition: "A UML state machine shows the legal states in one object's lifecycle and the events or conditions that permit each transition.",
    businessSummary: 'The life cycle stages that a record goes through (e.g. Draft -> Confirmed -> Completed), preventing illegal status jumps.',
    flowExplanation: [
      '1. A new record is created in its initial state (e.g. Draft or Pending).',
      '2. An approved action triggers a state change (e.g. paying moves an invoice to Paid).',
      '3. The system enforces strict rules: an invoice cannot jump from Cancelled to Completed without re-opening.',
      '4. The item eventually reaches its terminal, archived state.'
    ],
    keyTakeaways: [
      'Strict status transitions prevent business fraud and accidental double-charging.'
    ],
    drawingRules: [
      'Start from an initial pseudo-state and one explicitly modelled lifecycle field.',
      'Draw only legal from-state to to-state transitions stated by requirements.',
      'If transitions are absent, explain the evidence gap instead of inventing them.',
    ],
  },
  dfd: {
    question: 'What is a Data Flow Diagram?',
    definition: 'A data flow diagram shows how named information enters the system, is transformed by processes, is stored, and leaves for external entities.',
    businessSummary: 'A map tracking the journey of data into the application, how it is processed and calculated, and where it safely rests.',
    flowExplanation: [
      '1. Data enters from user input or external service feeds.',
      '2. Application processes clean, validate, and compute calculations on the data.',
      '3. Secure data stores preserve the verified information.',
      '4. Output data is formatted and served back to the user.'
    ],
    keyTakeaways: [
      'Data flows are tracked end-to-end to ensure zero data loss.'
    ],
    drawingRules: [
      'Start with external entities, numbered verb–noun processes, and data stores.',
      'Label every arrow with the actual data being moved.',
      'Avoid direct entity-to-store flow and black-hole or miracle processes.',
    ],
  },
  bpmn: {
    question: 'What is a BPMN Process Diagram?',
    definition: 'A BPMN process diagram models a business process with events, tasks, gateways, and participant lanes that make responsibility and hand-offs explicit.',
    businessSummary: 'A business process swimlane diagram making responsibilities between different team members and automated system tasks crystal clear.',
    flowExplanation: [
      '1. A triggering event (e.g. customer places an inquiry) starts the process.',
      '2. Tasks are routed to the specific lane of the person or system responsible.',
      '3. Decision gateways determine if supervisor approval or automated processing is required.',
      '4. The process reaches a documented business milestone.'
    ],
    keyTakeaways: [
      'Swimlanes eliminate confusion over who is responsible for each step.'
    ],
    drawingRules: [
      'Start with a named pool, horizontal responsibility lanes, and a start event.',
      'Place each task in the responsible participant lane and follow sequence flow.',
      'Use gateways only for explicit branches and finish with an end event.',
    ],
  },
  system_context: {
    question: 'What is a System Context Diagram?',
    definition: 'A system context diagram defines the software boundary and its externally visible relationships with people, external systems, and persistent data.',
    businessSummary: 'The 30,000-foot view of the entire software ecosystem: showing people on the outside, third-party partners, and the core app.',
    flowExplanation: [
      '1. Users and customers connect to the platform through mobile phones, tablets, or computers.',
      '2. The application acts as a secure castle wall, verifying every incoming visitor.',
      '3. Core business transactions and records are stored in a protected production database.',
      '4. External partner services (e.g. Stripe, AWS, notification gateways) communicate safely through dedicated APIs.'
    ],
    keyTakeaways: [
      'External parties can never bypass the application boundary to access the database directly.',
      'All user connections travel over encrypted, modern protocols.'
    ],
    drawingRules: [
      'Start with one central system boundary and keep internal detail minimal.',
      'Place people and external systems outside the boundary.',
      'Label supported interactions and omit unsupported integrations.',
    ],
  },
  component: {
    question: 'What is a Component Diagram?',
    definition: 'A UML component diagram shows modular software parts, the interfaces or ports through which they collaborate, and their required dependencies.',
    businessSummary: 'The structural anatomy of the app: showing how user screens, business logic engines, and database tables connect like Lego blocks.',
    flowExplanation: [
      '1. Screen components render the visual user interface.',
      '2. Clicking or typing on screens sends commands to backend API controllers.',
      '3. Security middleware checks credentials and sanitizes data.',
      '4. Database components store and retrieve records reliably.'
    ],
    keyTakeaways: [
      'Modular components ensure that modifying one screen does not break other parts of the system.'
    ],
    drawingRules: [
      'Start with presentation, application/domain, and data/external groups.',
      'Give each component one responsibility and connect dependencies through ports.',
      'Show provided or required interfaces only for supported service boundaries.',
    ],
  },
  deployment: {
    question: 'What is a Deployment Diagram?',
    definition: 'A UML deployment diagram shows runtime nodes, hosted software artifacts, and communication paths in the physical execution topology.',
    businessSummary: 'A map of the physical computers and cloud servers that run the software, showing how your app is hosted securely.',
    flowExplanation: [
      '1. The client browser runs the modern web frontend application.',
      '2. Requests travel securely across HTTPS to the production application server.',
      '3. The application server queries the database cluster over authenticated internal networks.'
    ],
    keyTakeaways: [
      'Zero sensitive keys or database passwords are ever exposed to the client browser.'
    ],
    drawingRules: [
      'Start with client, application host, and data host nodes required by the stack.',
      'Nest software artifacts inside the nodes on which they execute.',
      'Label protocols and add external nodes only when required by the SRS.',
    ],
  },
}

export const DIAGRAM_NOTATION = {
  use_case: ['Stick figure — actor', 'Oval — actor goal / use case', 'Rectangle — system boundary', 'Solid line — association'],
  sequence: ['Box and dashed line — participant lifeline', 'Solid arrow — request/call', 'Dashed arrow — return', 'Time runs top to bottom'],
  erd: ['Entity box — table and attributes', 'PK / FK — primary and foreign key', "Bar / crow's foot — one / many"],
  activity: ['Filled circle — initial node', 'Rounded rectangle — action', 'Diamond — decision or merge', 'Bullseye — final node'],
  class_object: ['Three-part box — class, attributes, operations', '+ / − — public / private', 'Association labels — multiplicity', 'Underlined name — object instance'],
  state_machine: ['Filled circle — initial pseudo-state', 'Rounded rectangle — state', 'Labeled arrow — legal transition', 'Bullseye — final pseudo-state'],
  dfd: ['Rectangle — external entity', 'Rounded process — data transformation', 'Open-ended box — data store', 'Labeled arrow — data flow'],
  bpmn: ['Thin / thick circle — start / end event', 'Rounded rectangle — task', 'Diamond — gateway', 'Pool and lanes — participant responsibility'],
  system_context: ['Central boundary — system in scope', 'Outside box — actor or external system', 'Cylinder — persistent data', 'Labeled arrow — external relationship'],
  component: ['Component glyph box — modular component', 'Square — port', 'Arrow — supported dependency', 'Bands — architectural layers'],
  deployment: ['3-D box — runtime node', 'Nested label — hosted artifact', 'Labeled line — communication path', 'Outside box — external service'],
}

export function guideForDiagram(kind) {
  const guide = DIAGRAM_GUIDE[kind] || {
    question: `What is this ${String(kind || 'diagram').replaceAll('_', ' ')}?`,
    definition: 'This view is derived from the approved software requirements.',
    drawingRules: ['Start with only the elements and relationships supported by the SRS.'],
  }
  return { ...guide, notation: DIAGRAM_NOTATION[kind] || [] }
}
