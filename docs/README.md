# Docs assets

Screenshots in [`assets/`](assets/) power the root README.

To regenerate desk shots without Alpaca keys or Kronos weights:

```bash
# terminal 1 — mock trader API (:8001)
node scripts/demo-snapshot-server.mjs

# terminal 2 — dashboard (:3033)
pnpm --filter @kronos/dashboard dev
```

Open http://localhost:3033, capture the desk, and replace files under `assets/`.
