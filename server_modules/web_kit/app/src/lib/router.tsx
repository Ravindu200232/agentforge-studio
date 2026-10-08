import * as React from "react";
import { routes, type RouteDef } from "@/routes";

// The app's routes live in the address hash (`#/orders`), so the whole app is one HTML file that can be opened from anywhere.
// `src/routes.ts` is written by the Studio from the specification: every screen, and the page file (`src/pages/<file>.tsx`) it is
// drawn in. A page is a component with a default export; link to another page with <Link to="/orders">.

type Params = Record<string, string>;

const split = (path: string) => path.split("/").filter(Boolean);

export function currentPath(): string {
  const raw = window.location.hash.replace(/^#/, "").split("?")[0];
  return "/" + split(raw).join("/");
}

const isParam = (part: string) => /^\[.+\]$/.test(part) || part.startsWith(":");

export function matchRoute(path: string): { route: RouteDef; params: Params } | null {
  const want = split(path);
  const same = (a: string, b: string) => a === b || decodeURIComponent(a) === decodeURIComponent(b);
  // A route written exactly as it is asked for wins over one with a parameter in it.
  const literal = routes.find((r) => split(r.route).length === want.length && split(r.route).every((p, i) => same(p, want[i])));
  if (literal) return { route: literal, params: {} };
  for (const route of routes) {
    const parts = split(route.route);
    if (parts.length !== want.length) continue;
    const params: Params = {};
    let ok = true;
    parts.forEach((part, i) => {
      if (isParam(part)) params[part.replace(/^\[|\]$|^:/g, "")] = decodeURIComponent(want[i]);
      else if (!same(part, want[i])) ok = false;
    });
    if (ok) return { route, params };
  }
  return null;
}

export function navigate(to: string) {
  const path = "/" + split(String(to || "/").split("#").pop()!.split("?")[0]).join("/");
  if (window.location.hash === "#" + path) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else window.location.hash = "#" + path;
}

export const useNavigate = () => navigate;

function subscribe(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function useLocation(): string {
  return React.useSyncExternalStore(subscribe, currentPath, () => "/");
}

const ParamsContext = React.createContext<Params>({});

/** The values in the address, for a route such as `/orders/[id]`: `useParams().id`. */
export const useParams = () => React.useContext(ParamsContext);

type LinkProps = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: string };

export const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link({ to, children, ...rest }, ref) {
  const path = "/" + split(String(to || "/").split("?")[0]).join("/");
  return (
    <a ref={ref} href={"#" + path} {...rest}>
      {children}
    </a>
  );
});

function NotBuilt({ route }: { route: RouteDef }) {
  return (
    <div className="mx-auto max-w-xl p-10 text-center text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{route.name}</p>
      <p className="mt-2 rounded-md border border-dashed p-6">
        This page is not made yet. Write <code>src/pages/{route.file}.tsx</code> (a component with a default export) for{" "}
        <code>{route.route}</code>.
      </p>
    </div>
  );
}

function NotFound({ path }: { path: string }) {
  return (
    <div className="mx-auto max-w-xl p-10 text-sm">
      <p className="font-medium">There is no page at {path}</p>
      <ul className="mt-3 list-disc pl-5 text-muted-foreground">
        {routes.map((r) => (
          <li key={r.route}>
            <Link to={r.route} className="underline">
              {r.name}
            </Link>{" "}
            <code>{r.route}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Router({ pages }: { pages: Record<string, { default?: React.ComponentType }> }) {
  const path = useLocation();
  const found = matchRoute(path);

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [path]);

  // The app never leaves its own page: a plain link to "/orders" opens that page, "#" and other sites do nothing, and a
  // form is never really sent.
  React.useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      const anchor = (event.target as Element | null)?.closest?.("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href") || "";
      if (href.startsWith("#/")) return;
      event.preventDefault();
      if (href.startsWith("/") && !href.startsWith("//")) navigate(href);
    };
    const onSubmit = (event: Event) => event.preventDefault();
    document.addEventListener("click", onClick);
    document.addEventListener("submit", onSubmit);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("submit", onSubmit);
    };
  }, []);

  if (!found) return <NotFound path={path} />;
  const Page = pages[found.route.file]?.default;
  if (!Page) return <NotBuilt route={found.route} />;
  return (
    <ParamsContext.Provider value={found.params}>
      <Page />
    </ParamsContext.Provider>
  );
}
