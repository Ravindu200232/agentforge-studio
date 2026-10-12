The React app in `{{app}}` failed validation. This is the build or browser error:

```
{{error}}
```

Read the affected source file and its imports, then fix the root cause. Use the actual public API of imported modules and installed package names. Change only what the error needs, and do not edit Studio-owned files such as `src/lib/session.tsx`. The Studio will rebuild and check the screens after this repair; if another error remains, you will receive it in the next turn. Do not run the skill's scripts or install packages.
