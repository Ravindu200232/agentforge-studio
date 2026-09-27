const field = property => ({property, label: property.replaceAll('-', ' ')})
const fields = list => list.split(' ').map(field)
export const STYLE_GROUPS = [
  {name: 'Typography', fields: fields('font-family font-size font-weight font-style line-height letter-spacing word-spacing text-align text-transform text-decoration-line text-decoration-color text-decoration-thickness text-underline-offset text-shadow text-indent white-space word-break overflow-wrap text-overflow')},
  {name: 'Colors & backgrounds', fields: fields('color background-color background-image background-size background-position background-repeat background-attachment background-blend-mode accent-color')},
  {name: 'Size & spacing', fields: fields('width height min-width max-width min-height max-height aspect-ratio padding padding-top padding-right padding-bottom padding-left margin margin-top margin-right margin-bottom margin-left gap row-gap column-gap')},
  {name: 'Layout & position', fields: fields('display position top right bottom left z-index box-sizing overflow overflow-x overflow-y float clear vertical-align visibility')},
  {name: 'Flex & grid', fields: fields('flex-direction flex-wrap justify-content align-items align-content align-self flex flex-grow flex-shrink flex-basis order grid-template-columns grid-template-rows grid-auto-columns grid-auto-rows grid-auto-flow grid-column grid-row justify-items justify-self place-items')},
  {name: 'Borders & effects', fields: fields('border border-width border-style border-color border-radius border-top-left-radius border-top-right-radius border-bottom-left-radius border-bottom-right-radius outline outline-offset box-shadow opacity filter backdrop-filter mix-blend-mode clip-path')},
  {name: 'Transform & interaction', fields: fields('transform transform-origin translate rotate scale transition transition-duration transition-timing-function animation cursor pointer-events user-select scroll-behavior scroll-margin-top scroll-snap-align touch-action')},
  {name: 'Images & media', fields: fields('object-fit object-position')},
]
const choices = {
  'font-weight': '100|200|300|400|500|600|700|800|900', 'font-style': 'normal|italic|oblique',
  'text-align': 'left|center|right|justify|start|end', 'text-transform': 'none|uppercase|lowercase|capitalize',
  'text-decoration-line': 'none|underline|overline|line-through', 'white-space': 'normal|nowrap|pre|pre-wrap|pre-line|break-spaces',
  'display': 'block|inline|inline-block|flex|inline-flex|grid|inline-grid|contents|none', 'position': 'static|relative|absolute|fixed|sticky',
  'box-sizing': 'border-box|content-box', 'overflow': 'visible|hidden|auto|scroll|clip', 'visibility': 'visible|hidden|collapse',
  'flex-direction': 'row|column|row-reverse|column-reverse', 'flex-wrap': 'nowrap|wrap|wrap-reverse',
  'justify-content': 'start|end|center|space-between|space-around|space-evenly', 'align-items': 'stretch|start|end|center|baseline',
  'grid-auto-flow': 'row|column|row dense|column dense', 'border-style': 'none|solid|dashed|dotted|double|groove|ridge|inset|outset',
  'object-fit': 'fill|contain|cover|none|scale-down', 'cursor': 'auto|pointer|default|text|move|grab|grabbing|not-allowed|crosshair',
  'pointer-events': 'auto|none', 'user-select': 'auto|none|text|all',
}
for (const group of STYLE_GROUPS) for (const item of group.fields) if (choices[item.property]) item.options = choices[item.property].split('|')
export const ATTRIBUTES = ['id','class','title','role','aria-label','tabindex']
export const MEDIA_ATTRIBUTES = ['src','alt','width','height','loading','poster']
export const FORM_ATTRIBUTES = ['name','type','placeholder','value','min','max','step','pattern','autocomplete']
