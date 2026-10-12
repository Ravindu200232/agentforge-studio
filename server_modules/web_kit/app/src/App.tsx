import { Router } from "@/lib/router";
import { SessionProvider } from "@/lib/session";

// Every file in src/pages is a screen: `src/pages/<file>.tsx` for the route that `src/routes.ts` gives that file. Add shared
// pieces (a layout, a navigation bar, charts) anywhere else under src/ and import them into the pages.
const modules = import.meta.glob("./pages/**/*.{tsx,jsx}", { eager: true }) as Record<string, { default?: React.ComponentType }>;
const pages = Object.fromEntries(
  Object.entries(modules).map(([file, module]) => [file.replace(/^\.\/pages\//, "").replace(/\.(tsx|jsx)$/, ""), module]),
);

export default function App() {
  return (
    <SessionProvider>
      <Router pages={pages} />
    </SessionProvider>
  );
}
