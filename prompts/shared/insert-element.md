Add one element to the wireframe on `{{route}}` in `{{app}}`.

{{source}}

The JSON identifies the shape, surrounding container, requested bounds and viewport. Use `bounds.x` and `bounds.y` as document coordinates. When positioning the element relative to the identified container, use `offset_within_target` as the local offset from its outer top left and account for any container border. Treat the text value as literal content.

{{details}}

Add a grayscale rectangle, ellipse, or text box as requested. Use a 1px dark gray outline and a light gray fill. Use a 50% border radius for an ellipse and 8px of padding for a text box. Render textbox text as escaped literal text with normal wrapping. Use the captured size and position in the specified viewport and make it fit a narrower container. Keep changes local to this page and preserve the existing content, navigation, and interactions.
