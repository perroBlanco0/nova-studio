---
name: qa-nova-studio
description: How to QA the deployed NOVA Studio app (video.byrongonzalez.dev on Render) — viewport tricks, crash-prone endpoint, known UI quirks
---

# QA: NOVA Studio (video.byrongonzalez.dev)

FastAPI + single-file `static/index.html` app deployed on Render free tier. Repo checkout: `~/nova/app` (local copy may lag behind deployed HTML — always `curl https://video.byrongonzalez.dev/` and diff before assuming UI structure).

## Mobile viewport at 375px
Chrome on this box enforces a min window width of ~680px, so `wmctrl -e` cannot reach 375. Two options:
1. Dock DevTools (F12) and widen the window until the page viewport is ~380px (`matchMedia('(max-width:640px)')` then applies).
2. Or drive CDP over the existing debugging port with playwright:
   `p.chromium.connect_over_cdp("http://localhost:29229")` → find page `x.url.startswith("https://video.byrongonzalez")` → `new_cdp_session` → `Emulation.setDeviceMetricsOverride {width:375,height:700,deviceScaleFactor:2,mobile:true}`. NOTE: the override is session-scoped — it clears when the script exits; keep the process alive if you need it to persist.
3. Verify overflow objectively: `({iw:innerWidth, sw:document.documentElement.scrollWidth})` via `page.evaluate` — browser_console may attach to the wrong tab since there are many tabs/windows open.

## Known traps
- `POST /api/video` blocks until the render finishes (1–5 min) and (as of Sep 2026) hard-crashes the service ~30s in → empty-body 502; whole site 502s for ~1–2 min while Render restarts. Wait ~60–90s and retry if you see this.
- `POST /api/character` returns instantly with a Pollinations URL; the `<img>` itself takes 30–60s to render. CTA appears before the image is visible.
- The Vidu toggle (`.togg`) has a double-toggle bug: clicking directly on the checkbox input is a no-op; click the row instead.
- Native `alert()` dialogs are used for validation — dismiss with Return before continuing.
- The Vidu browser tab open in the second Chrome window belongs to the user's own account — do not close or alter it.

## Devin Secrets Needed
- None — the site and API are unauthenticated.
