// Whether a saved diagram source is Mermaid at all. A source is when one of its lines is a diagram declaration - the
// same test as `_OPENER_LINE` in server_modules/mermaid.py, so the server and the screen agree. What a model said
// instead of drawing ("Let me read the Booking module…") is not one, and the screen never shows it as code.
const DECLARATION = /^[ \t]*(?:(?:flowchart|graph)(?:[ \t]+(?:TB|TD|BT|RL|LR))?|sequenceDiagram|classDiagram(?:-v2)?|stateDiagram(?:-v2)?|erDiagram)[ \t]*;?[ \t]*\r?$/im

export const isMermaid = (source) => DECLARATION.test(String(source || ''))
