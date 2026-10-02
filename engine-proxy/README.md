# AgentForge engine

A Cloudflare Worker that stands between AgentForge and ollama.com, so the ollama.com API key is never in the app.

```
AgentForge app  --(app token)-->  this Worker  --(ollama.com key)-->  ollama.com
```

- The key is the Worker secret `OLLAMA_API_KEY`. It is set in Cloudflare and stored only there.
- Every copy of the app sends `APP_TOKEN`. The app keeps the same value in `server_modules/engine.json`.
  - The token ships with the app, so it only keeps out callers who do not have the app.
  - Each address is also rate limited (`wrangler.toml`).
- Only the calls the app makes are passed through: chat, model details and list, web search and web fetch.

## Set up (once)

From this folder:

```bash
npx wrangler login
```

```bash
npx wrangler secret put OLLAMA_API_KEY
```

Paste the key when asked. It goes straight to Cloudflare.

```bash
npx wrangler secret put APP_TOKEN
```

Use the `token` value from `server_modules/engine.json`.

```bash
npx wrangler deploy
```

The deploy prints the Worker's address (`https://agentforge-engine.<your-subdomain>.workers.dev`). That address is
the `url` in `server_modules/engine.json`.

## If the key or the token leaks

- **Key:** make a new key on ollama.com, then run `npx wrangler secret put OLLAMA_API_KEY` again. The app does not
  change.
- **Token:** put a new value in `engine.json` and in `APP_TOKEN`, then publish a new release. Older copies of the app
  stop reaching the engine.

Also set a usage limit on the ollama.com account.
