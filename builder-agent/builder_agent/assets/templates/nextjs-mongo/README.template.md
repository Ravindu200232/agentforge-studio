# Scaffolded from the verified Next.js + MongoDB template

Everything here was installed, unit-tested, seeded, built, started and opened
in a browser before it was made a template. Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page, route and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

`lib/db.js` holds the cached connection — import `connectDb` from it rather
than calling `mongoose.connect` anywhere else. Models go in `models/`, data
access in `lib/`, and any page or route handler that reads the database needs
`export const dynamic = 'force-dynamic'`.
