#!/usr/bin/env python
"""Local PNG renderer. Bypasses browser/MOTW. Usage:
    python render_cards.py cards.html out/
"""
import sys, os, pathlib
from playwright.sync_api import sync_playwright

def render(html_path, out_dir, width=1080, height=1350):
    html_path = os.path.abspath(html_path)
    os.makedirs(out_dir, exist_ok=True)
    file_url = pathlib.Path(html_path).as_uri()
    base = os.path.splitext(os.path.basename(html_path))[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        ctx = browser.new_context(
            viewport={"width": width + 80, "height": height + 100},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(file_url, wait_until="networkidle")
        page.wait_for_timeout(1500)

        cards = page.locator(".card")
        count = cards.count()
        for i in range(count):
            page.evaluate(
                """async (idx) => {
                    const card = document.querySelectorAll('.card')[idx];
                    card.style.position='fixed'; card.style.left='0'; card.style.top='0';
                    card.style.width='1080px'; card.style.height='1350px';
                    card.style.zIndex='99999'; card.style.overflow='hidden'; card.style.margin='0';
                    await new Promise(r => setTimeout(r, 250));
                    if (window.autofitCard) await window.autofitCard(card);
                    await new Promise(r => setTimeout(r, 100));
                }""",
                i,
            )
            out_path = os.path.join(out_dir, f"{base}-{i+1:02d}.png")
            cards.nth(i).screenshot(path=out_path)
            print(f"  -> {out_path}")
            page.evaluate(
                "(idx) => document.querySelectorAll('.card')[idx].removeAttribute('style')",
                i,
            )
        browser.close()

if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
