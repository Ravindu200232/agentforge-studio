# Demo accounts for the prototype

This product has sign-in, so the prototype needs one demo account for every role, so
a reviewer can enter as each of them. They are shown on the sign-in page, used by the
kit's demo sign-in, and listed for the customer when the prototype is finished. They
are obviously fictitious and never real secrets.

For each role:

- `display_name` — a plausible person's name for that role;
- `email` — on the reserved domain `example.com`, in a style that suits the product;
- `password` — obviously a demo value that meets the specification's password rule
  (for example a short phrase with a number), never a real-looking secret;
- `lands_on` — the route that role opens first after signing in, taken from the
  journeys and the sitemap. It must be one of the routes listed below.

Return JSON only, nothing before or after it:

```json
{"accounts": [{"role": "…", "role_key": "…", "display_name": "…", "email": "…", "password": "…", "lands_on": "/…"}]}
```

## Roles

{{roles}}

## Sign-in

{{sign_in}}

## Routes

{{routes}}

## Journeys

{{journeys}}
