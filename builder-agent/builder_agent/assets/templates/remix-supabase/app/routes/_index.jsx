/**
 * Replace this route.
 *
 * It exists so the scaffold builds and renders before a single feature is
 * written: an empty bundle and a broken one look identical from the outside,
 * and finding out which one you have is worth the ten seconds it costs.
 *
 * `_index.jsx` is the route for `/`. The leading underscore is Remix's
 * convention for a segment that does not appear in the URL — a file called
 * `index.jsx` would instead serve `/index`.
 */
export default function HomeRoute() {
  return (
    <main>
      <h1>Application</h1>
      <p>Replace this route with the real home screen.</p>
    </main>
  );
}
