# AgentForge 1.0.3 for macOS (Apple Silicon)

Download the DMG and drag AgentForge to Applications. It is the same AgentForge Studio as the Windows 1.0.3 release.

## Faster from the interview to deployment

- **Interview:** the next question comes in about two seconds; what your answer means is filed in the background while you read the question.
- **Specification:** written in parts at the same time and joined (a 31-page store: 9 minutes before, about 2½ now). The check of the diagram pictures finishes in the background.
- **Build:** pages are built by three agents at the same time once the foundation stands; the unit tests and the journey tests are written together.
- **Tests:** each end-to-end journey runs on its own, at desktop width, and is fixed and run again straight away before the next one; the prototype's journey walk works the same way.
- **Deployment:** fewer rounds; the web is searched only for what the deployment skill pages do not answer.

## Test results you can trust

- Requirements are marked met from the tests' own results (the journeys through their pages, or a test named after the requirement), never from what the builder wrote before testing.
- The build writes a test for every requirement on a page no journey goes through.
- A journey that fails only at phone width is a warning, not a failed test.

## Also

- A fix that leaves the prototype not bundling no longer stops the journey test: it is repaired again, and the other journeys are still clicked through.

- The specification keeps to what you asked for: a page whose address differs only in capital letters is no longer a second page.
- Names of people stay out of the model; words like Admin, Password or Require are never taken for names.
- Everything in the Mac 1.1.0 release (Supabase sign-in through the official CLI, verified email sign-up, cloud reply recovery).

The app bundles Python 3.12, Node.js 24, the privacy runtime, and Playwright Chromium. Supabase integration also requires the official CLI: brew install supabase/tap/supabase.

The app is ad-hoc signed but not Apple-notarized. If macOS blocks the first launch, Control-click AgentForge and choose Open.
