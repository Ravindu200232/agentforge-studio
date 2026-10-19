The runtime test failed after the last changes: the application has to build, and every page has to open (each page anyone can open answers and shows its content; each protected page turns a signed-out visitor away). This is what it said:

```
{{output}}
```

Find the cause in the application's source and fix it, changing only what the failure needs. Check the fix with `npm run build`. Do not run the journeys or any other test: the Studio runs the runtime test again itself.
