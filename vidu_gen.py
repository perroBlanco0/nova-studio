"""Generate a real animated clip on vidu.com using the logged-in Chrome session via CDP.
Returns local mp4 path or raises."""
import asyncio
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

CDP = "http://localhost:29229"
CREATE_URL = "https://www.vidu.com/create/img2video"


async def _vidu_page(browser):
    pages = [pg for c in browser.contexts for pg in c.pages]
    for pg in pages:
        if pg.url.startswith("https://www.vidu.com/create/img2video"):
            return pg
    for pg in pages:
        if "vidu.com" in pg.url:
            await pg.goto(CREATE_URL)
            await pg.wait_for_timeout(5000)
            return pg
    ctx = browser.contexts[0]
    pg = await ctx.new_page()
    await pg.goto(CREATE_URL)
    await pg.wait_for_timeout(5000)
    return pg


async def _click_text(pg, text, idx=-1):
    ok = await pg.evaluate(
        """(t, i) => {
            const e = [...document.querySelectorAll('*')].filter(
              e => e.children.length === 0 && (e.innerText || '').trim() === t);
            if (!e.length) return false;
            e[i < 0 ? e.length + i : i].click();
            return true;
        }""", text, idx)
    return ok


_VIDEO_SRCS_JS = """() => [...document.querySelectorAll('video')]
    .map(v => v.src || v.currentSrc)
    .filter(s => s && (s.includes('infer') || s.endsWith('.mp4')))"""


async def generate(image: Path, motion_prompt: str, out_mp4: Path,
                   timeout_s: int = 300) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        pg = await _vidu_page(browser)

        # videos already on the page (previous generations, gallery history)
        # — must be excluded below so we don't return a stale clip instead
        # of waiting for the one we're about to create.
        seen_before = set(await pg.evaluate(_VIDEO_SRCS_JS))

        # upload reference image
        fi = pg.locator('input[type=file]').first
        await fi.set_input_files(str(image))
        await pg.wait_for_timeout(9000)

        # close any reference-mention dialog that pops (Cancel)
        try:
            await pg.locator('button:has-text("Cancel")').click(timeout=3000)
        except Exception:
            pass

        # motion prompt — never contains '@' (triggers ref dialog)
        t = pg.locator('textarea').first
        await t.click()
        await t.fill(motion_prompt.replace('@', ''))
        await pg.wait_for_timeout(800)

        await pg.locator('button:has-text("Create")').first.click()
        await pg.wait_for_timeout(4000)

        # poll for the generated infer video — must be a URL that wasn't
        # already on the page before this generation started.
        vid_url = None
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            vids = await pg.evaluate(_VIDEO_SRCS_JS)
            new_vids = [v for v in vids if v not in seen_before]
            if new_vids:
                vid_url = new_vids[0]
                break
            body = await pg.inner_text('body')
            if 'nsufficient' in body or 'nnot submit' in body:
                raise RuntimeError('vidu: no credits / queue full')
            await pg.wait_for_timeout(5000)
        if not vid_url:
            raise RuntimeError('vidu: generation timeout')

    req = urllib.request.Request(vid_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out_mp4, "wb") as f:
        f.write(r.read())
    return out_mp4


def generate_sync(image: Path, motion_prompt: str, out_mp4: Path) -> Path:
    return asyncio.run(generate(image, motion_prompt, out_mp4))
