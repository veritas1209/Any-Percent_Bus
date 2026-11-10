"""Render the repository-native SVG mark to platform icon sizes, with no external art."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]


async def run():
    svg=(ROOT/'app/assets/branding/icon.svg').read_text()
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=await browser.new_page()
        await page.set_content('<style>html,body{margin:0;width:100%;height:100%}svg{width:100%;height:100%}</style>'+svg)
        files={
            'app/web/favicon.png':32,
            'app/web/icons/Icon-192.png':192,'app/web/icons/Icon-512.png':512,
            'app/web/icons/Icon-maskable-192.png':192,'app/web/icons/Icon-maskable-512.png':512,
            **{f'app/android/app/src/main/res/mipmap-{density}/ic_launcher.png':size for density,size in [('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)]},
        }
        for name,size in files.items():
            await page.set_viewport_size({'width':size,'height':size})
            await page.screenshot(path=str(ROOT/name))
        await browser.close()
    print('Rendered',len(files),'platform icons')


if __name__=='__main__':asyncio.run(run())
