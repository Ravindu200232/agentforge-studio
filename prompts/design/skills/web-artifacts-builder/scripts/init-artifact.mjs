#!/usr/bin/env node
// Node port of init-artifact.sh for machines without bash (the AgentForge desktop app).
// Same result as the official script: a React 18 + TypeScript + Tailwind CSS 3.4 + shadcn/ui
// project with the 40+ shadcn components unpacked into src/ and the "@/" alias set up.
// The one difference: instead of running pnpm installs it links node_modules to the shared
// dependency store (see lib.mjs), so it works offline and takes seconds.
//
//   node init-artifact.mjs <project-name>      create the project in ./<project-name>
//   node init-artifact.mjs --prepare           only make sure the shared store is installed
import fs from 'node:fs'
import path from 'node:path'
import { scriptsDir, fail, runtimeDir, runtimePackage, ensureRuntime, linkNodeModules, extractTarGz } from './lib.mjs'

const args = process.argv.slice(2)
const nodeMajor = Number(process.versions.node.split('.')[0])
if (nodeMajor < 18) fail('Node.js 18 or higher is required (found ' + process.version + ')')

const store = runtimeDir()
ensureRuntime(store)
if (args.includes('--prepare')) {
  console.log('Shared UI toolkit ready: ' + store)
  process.exit(0)
}

const name = args.find((a) => !a.startsWith('--'))
if (!name) fail('Usage: node init-artifact.mjs <project-name>')

const tarball = path.join(scriptsDir, 'shadcn-components.tar.gz')
if (!fs.existsSync(tarball)) fail('shadcn-components.tar.gz not found next to this script: ' + tarball)

const dir = path.resolve(name)
const title = path.basename(dir)
if (fs.existsSync(dir) && fs.readdirSync(dir).length) fail(name + ' already exists and is not empty')

console.log('Creating new React + Vite project: ' + name)

const put = (rel, text) => {
  const file = path.join(dir, rel)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, text)
}

const pkg = runtimePackage()
put(
  'package.json',
  JSON.stringify(
    {
      name: title.toLowerCase().replace(/[^a-z0-9-_.]+/g, '-') || 'artifact',
      private: true,
      version: '0.0.0',
      scripts: { bundle: 'node ' + JSON.stringify(path.join(scriptsDir, 'bundle-artifact.mjs')) },
      dependencies: pkg.dependencies,
      devDependencies: pkg.devDependencies,
    },
    null,
    2
  ) + '\n'
)

// `npm install` inside an app would reshape the shared store through the link, so it is refused.
put(
  '.npmrc',
  '# Dependencies are provided by the shared store linked at node_modules. Do not install here.\ndry-run=true\n'
)
put('.gitignore', 'node_modules\ndist\n.parcel-cache\nbundle.html\n')
// Parcel takes the nearest folder holding a lockfile as its project root and resolves the
// absolute "/src/main.tsx" in index.html against it. Without one it climbs to the enclosing
// repository (the workspace usually sits inside one) and fails to find the entry.
put('package-lock.json', JSON.stringify({ name: title, lockfileVersion: 3, requires: true, packages: {} }, null, 2) + '\n')

put(
  'index.html',
  `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${title.replace(/[<>&]/g, '')}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
`
)

put(
  'src/main.tsx',
  `import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
`
)

put(
  'src/App.tsx',
  `export default function App() {
  return <div className="p-8">${title.replace(/[<>&{}]/g, '')}</div>
}
`
)

put(
  'src/vite-env.d.ts',
  `/// <reference types="vite/client" />

// Parcel inlines these into bundle.html: import hero from 'data-url:./assets/hero.png'
declare module 'data-url:*' {
  const url: string
  export default url
}
`
)

put(
  'postcss.config.js',
  `module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
`
)

put(
  'tailwind.config.js',
  `/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
`
)

put(
  'src/index.css',
  `@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 0 0% 3.9%;
    --card: 0 0% 100%;
    --card-foreground: 0 0% 3.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 0 0% 3.9%;
    --primary: 0 0% 9%;
    --primary-foreground: 0 0% 98%;
    --secondary: 0 0% 96.1%;
    --secondary-foreground: 0 0% 9%;
    --muted: 0 0% 96.1%;
    --muted-foreground: 0 0% 45.1%;
    --accent: 0 0% 96.1%;
    --accent-foreground: 0 0% 9%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 89.8%;
    --input: 0 0% 89.8%;
    --ring: 0 0% 3.9%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 0 0% 3.9%;
    --foreground: 0 0% 98%;
    --card: 0 0% 3.9%;
    --card-foreground: 0 0% 98%;
    --popover: 0 0% 3.9%;
    --popover-foreground: 0 0% 98%;
    --primary: 0 0% 98%;
    --primary-foreground: 0 0% 9%;
    --secondary: 0 0% 14.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 0 0% 14.9%;
    --muted-foreground: 0 0% 63.9%;
    --accent: 0 0% 14.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 0 0% 14.9%;
    --input: 0 0% 14.9%;
    --ring: 0 0% 83.1%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
`
)

// One tsconfig carries the "@/" alias for the editor, tsc and parcel-resolver-tspaths.
put(
  'tsconfig.json',
  JSON.stringify(
    {
      compilerOptions: {
        target: 'ES2020',
        useDefineForClassFields: true,
        lib: ['ES2020', 'DOM', 'DOM.Iterable'],
        module: 'ESNext',
        skipLibCheck: true,
        moduleResolution: 'bundler',
        allowImportingTsExtensions: true,
        resolveJsonModule: true,
        isolatedModules: true,
        noEmit: true,
        jsx: 'react-jsx',
        strict: true,
        noFallthroughCasesInSwitch: true,
        baseUrl: '.',
        paths: { '@/*': ['./src/*'] },
      },
      include: ['src'],
    },
    null,
    2
  ) + '\n'
)

put(
  'vite.config.ts',
  `import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
`
)

put(
  'components.json',
  `{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
`
)

console.log('Extracting shadcn/ui components...')
const files = extractTarGz(tarball, path.join(dir, 'src'))
linkNodeModules(dir, store)

console.log('')
console.log('Setup complete: ' + dir)
console.log(files + ' shadcn/ui component files unpacked into src/ (accordion, alert, avatar, badge, button, calendar,')
console.log('card, carousel, checkbox, command, dialog, drawer, dropdown-menu, form, input, popover, select, sheet,')
console.log('skeleton, slider, sonner, switch, table, tabs, textarea, toast, tooltip and more).')
console.log('Also available: react-router-dom, framer-motion, recharts, lucide-react, react-hook-form, zod, date-fns.')
console.log('')
console.log("Import components like: import { Button } from '@/components/ui/button'")
console.log('Dependencies are already provided (node_modules links to the shared store). Do not run npm install.')
console.log('When the app is ready: cd ' + name + ' && node ' + path.join(scriptsDir, 'bundle-artifact.mjs'))
