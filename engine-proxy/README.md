# AgentForge engine

A Cloudflare Worker that stands between AgentForge and ollama.com, so the ollama.com API key is never in the app.
It is also the broker for "Sign in with Supabase" (below), so nobody who installs AgentForge registers an OAuth app.

```
AgentForge app  --(app token)-->  this Worker  --(ollama.com key)-->  ollama.com
```

- The key is the Worker secret `OLLAMA_API_KEY`. It is set in Cloudflare and stored only there.
- Every copy of the app sends `APP_TOKEN`. The app keeps the same value in `server_modules/engine.json`.
  - The token ships with the app, so it only keeps out callers who do not have the app.
  - Each address is also rate limited (`wrangler.toml`).
- Only the calls the app makes are passed through: chat, model details and list, web search and web fetch, and the
  account balance (`GET /api/balance`), which the AgentForge admin app shows.

## Streaming replies and credit

The production Worker is `agentforge-engine` at
`https://agentforge-engine.engine-proxy.workers.dev`. Installed desktop apps already use this URL. Deploying this Worker
updates those apps without rebuilding or changing their configuration.

For chat and generation, the Worker forwards each upstream byte unchanged. It keeps only the last 8 KB for the final
usage record and schedules credit settlement when the response stream finishes. It does not parse every token fragment
or wait for the credit service before closing the model reply. Keep settlement tied to the response stream: moving the
stream reader into a `waitUntil` task can leave reservations open on long replies. If the final provider usage record is
missing, the Worker releases the reservation instead of estimating tokens from NDJSON framing bytes. The admin service
recovers any abandoned reservations.

On the current Workers Free plan, a very long response can outlive the background accounting task. The model reply
still reaches the app; the admin service releases a leftover reservation when account status is read after 15 minutes.
Exact metering for these unusually long calls requires a separate meter with a longer execution budget or a Workers
Paid plan. The Free plan's 10 ms CPU limit is too small for a JavaScript wrapper around every chunk of a large reply.

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

Use the `token` value from `server_modules/engine.json`.

```bash
npx wrangler deploy
```

The deploy prints the Worker's address (`https://agentforge-engine.<your-subdomain>.workers.dev`). That address is
the `url` in `server_modules/engine.json`.

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
- **Token:** put a new value in `engine.json` and in `APP_TOKEN`, then publish a new release. Older copies of the app
  stop reaching the engine.
- **Supabase client secret:** create a new secret on the OAuth app in Supabase, then run
  `npx wrangler secret put SUPABASE_CLIENT_SECRET` again. The app does not change.

Also set a usage limit on the ollama.com account.
