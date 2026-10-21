import os
import re
import subprocess
import threading

from dotenv import load_dotenv
from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from playwright.async_api import async_playwright

load_dotenv()

host = os.getenv("HOST", "127.0.0.1")
port = int(os.getenv("PORT", "8080"))
tunnel = os.getenv("TUNNEL_TOKEN")

chrome_path = os.getenv("CHROME_PATH")
user_agent = os.getenv("USER_AGENT")


def cloudflare_tunnel():
    subprocess.run(
        f"cloudflared tunnel run --token {tunnel}",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=cloudflare_tunnel, daemon=True).start()

    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        executable_path=chrome_path,
        chromium_sandbox=True,
        ignore_default_args=["--enable-automation"],
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-quic",
            "--disable-background-networking",
            "--disable-domain-reliability",
            "--disable-client-side-phishing-detection",
            "--disable-features=Translate",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-notifications",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--metrics-recording-only",
            "--password-store=basic",
            "--hide-crash-restore-bubble",
            "--use-mock-keychain",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-non-proxied-udp",
            "--blink-settings=imagesEnabled=false",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--force-device-scale-factor=0.5",
            "--fingerprint-random",
            "--fingerprint-device-scale-factor=1",
            "--fingerprint-screen=1920x1080",
            "--fingerprint-hardware-concurrency=8",
            "--fingerprint-device-memory=8",
        ]
    )

    app.state.browser = browser

    yield

    try:
        if browser.is_connected():
            await browser.close()
    except:
        pass

    try:
        await playwright.stop()
    except:
        pass


app = FastAPI(lifespan=lifespan)


class CookieSolver(BaseModel):
    site_url: str
    site_key: str

class CaptchaSolver(BaseModel):
    site_url: str
    captcha_url: str


def error_response(error: Exception, challenge: str):
    clean_error = (
        "Request timed out while waiting for challenge response."
        if "Timeout" in str(error)
        else f"Failed to process {challenge} challenge."
    )

    return JSONResponse(
        status_code=201,
        content={
            "status": 201,
            "error": clean_error
        }
    )

@app.post("/v1/cookie")
async def cookie_solver(data: CookieSolver):
    page = await app.state.browser.new_page()
    origin = "/".join(data.site_url.split("/", 3)[:3])

    page_html = f"""
    <html>
        <body>
            <script>
                window.ddjskey = "{data.site_key}";
            </script>
            <script src="https://js.datadome.co/tags.js" async></script>
        </body>
    </html>
    """

    try:
        await page.route(
            origin,
            lambda route: route.fulfill(body=page_html)
        )

        async with page.expect_response("**/js/") as info:
            await page.goto(origin, wait_until="commit")

        result = await (await info.value).json()
        result["user_agent"] = user_agent

        return result

    except Exception as error:
        return error_response(error, "cookie")

    finally:
        await page.close()

@app.post("/v1/captcha")
async def captcha_solver(data: CaptchaSolver):
    page = await app.state.browser.new_page()
    origin = "/".join(data.site_url.split("/", 3)[:3])

    page_html = f"""
    <html>
        <body>
            <script>
                const iframe = document.createElement("iframe");
                iframe.src = "{data.captcha_url}";
                iframe.style.width = "100%";
                iframe.style.height = "500px";
                iframe.style.border = "none";
                document.body.appendChild(iframe);
            </script>
        </body>
    </html>
    """

    try:
        await page.add_init_script(path="preload.js")

        await page.route(
            origin,
            lambda route: route.fulfill(body=page_html)
        )

        async with page.expect_response(
            re.compile(r"/captcha/check|/interstitial/(?!\?)")
        ) as info:
            await page.goto(origin, wait_until="commit")

            frame = page.frame_locator("iframe")
            body = await frame.locator("body").inner_text()

            if "Access is temporarily restricted" in body:
                raise

        result = await (await info.value).json()
        result.pop("view", None)
        result.pop("url", None)

        return {
            "status": 200,
            **result,
            "user_agent": user_agent
        }

    except Exception as error:
        return error_response(error, "captcha")

    finally:
        await page.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port
    )
