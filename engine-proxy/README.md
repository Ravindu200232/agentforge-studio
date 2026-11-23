# Legacy AgentForge engine

Current Studio installs use direct provider connections from **Settings → AI
Providers**. This Worker is available to earlier desktop releases and
installations that explicitly configure the legacy account service and engine.

A Cloudflare Worker that stands between AgentForge and ollama.com, so the ollama.com API key is never in the app.
It is also the broker for "Sign in with Supabase" (below), so nobody who installs AgentForge registers an OAuth app.

```
AgentForge app  --(app token)-->  this Worker  --(private server call)-->  Vercel admin  -->  ollama.com
```

- The key is the Worker secret `OLLAMA_API_KEY`. For model calls the Worker sends it to the authenticated Vercel admin service over HTTPS; neither the key nor the metering secret reaches the desktop app.
- Clients of this Worker send its `APP_TOKEN`.
  - Each address is also rate limited (`wrangler.toml`).
- Only the calls the app makes are passed through: chat, model details and list, web search and web fetch, and the
  account balance (`GET /api/balance`), which the AgentForge admin app shows.

## Streaming replies and credit

The production Worker is `agentforge-engine` at
`https://agentforge-engine.engine-proxy.workers.dev`. Earlier desktop releases use this URL.

For chat and generation, the Worker authenticates the app, rate limits the request, and streams bytes to and from the
Vercel admin service. Vercel checks account credit and the permitted model, reserves credit, calls Ollama, then reads
the final provider token counts and settles the charge. The Worker no longer parses the model request or reads model
reply chunks in JavaScript. The admin service releases a stale reservation if a model stream ends unexpectedly.

Vercel's function duration limit still applies to a single long model call; monitor this before increasing model
output or context limits. The public Worker URL stays unchanged for installed apps.

Before deploying, run `node --test test/meter.test.mjs` and `node ../tests/test_engine_proxy_oauth.mjs`. After deploying,
verify a long streamed model reply, account credit settlement, and the Supabase OAuth callback at the existing URL.

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

Use the value that your legacy clients are configured to send.

```bash
npx wrangler deploy
```

The deploy prints the Worker's address. Set `AGENTFORGE_ENGINE_URL` to that address and `AGENTFORGE_ENGINE_TOKEN`
to the corresponding app token on each client that still uses this Worker.

## Sign in with Supabase (once, by whoever publishes AgentForge)

Supabase will not exchange a sign-in for tokens without the OAuth app's client secret, and a secret cannot ship inside an
app everyone installs. So you register **one** Supabase OAuth app, this Worker keeps its secret, and every person who
installs AgentForge just clicks "Sign in with Supabase", approves in the browser and is done: no client id, no OAuth
app of their own, no callback URL to type.

```
AgentForge --start--> Worker --authorize link--> browser --> supabase.com
supabase.com --> Worker /oauth/supabase/callback --> browser --> AgentForge (on this computer)
AgentForge --code + PKCE verifier--> Worker (adds the client secret) --> supabase.com --> tokens
```

The Worker stores nothing. The sign-in state is signed with the secret and lapses after ten minutes, the browser is only
ever sent back to `http://localhost:<port>/.../supabase-oauth/callback`, and the PKCE verifier stays in the app.

1. In the Supabase dashboard open your organisation, **OAuth Apps**, **Publish a new OAuth application**:
   - **Application name:** AgentForge Studio
   - **Website URL:** your website
   - **Authorization callback URLs:** `https://agentforge-engine.<your-subdomain>.workers.dev/oauth/supabase/callback`
     (the Worker's address from the deploy above, with that path; it is the only callback you register)
   - **Permissions:** what AgentForge does for a person: read organisations, read and write projects, read the
     project API keys (the Supabase CLI's `orgs list`, `projects create` and `projects api-keys`). The permissions
     are fixed when the app is created, so give it all of those now.
2. Copy the **Client ID** into `wrangler.toml` as `SUPABASE_CLIENT_ID`.
3. Store the **Client Secret** in Cloudflare, where it stays:

```bash
npx wrangler secret put SUPABASE_CLIENT_SECRET
```

```bash
npx wrangler deploy
```

If you serve the Worker from your own domain, also set `PUBLIC_URL` (for example `https://engine.example.com`) to the
address the callback URL above uses.

Until this is done, AgentForge still works: a copy with no broker asks for an OAuth app of its own, as before.

## If the key or the token leaks

- **Key:** make a new key on ollama.com, then run `npx wrangler secret put OLLAMA_API_KEY` again. The app does not
  change.
- **Token:** update the clients' matching token and the Worker's `APP_TOKEN`. Older copies of the app
  stop reaching the engine.
- **Supabase client secret:** create a new secret on the OAuth app in Supabase, then run
  `npx wrangler secret put SUPABASE_CLIENT_SECRET` again. The app does not change.

Also set a usage limit on the ollama.com account.
