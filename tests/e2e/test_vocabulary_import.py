from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Error, Page, sync_playwright


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    database_path = tmp_path_factory.mktemp("e2e") / "wordstream.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path}",
        "ENVIRONMENT": "test",
        "AUTH_MODE": "disabled",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_ready(f"{base_url}/api/v1/health", process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not installed: {exc}")
        yield browser
        browser.close()


@pytest.fixture
def mobile_page(browser: Browser) -> Iterator[Page]:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    yield page
    page.close()


def test_paste_preview_confirm_and_phrase_detail(
    mobile_page: Page,
    live_server: str,
) -> None:
    mobile_page.goto(f"{live_server}/vocabularies/import")
    form = mobile_page.locator('form[data-mode="paste"]')
    form.locator('input[name="name"]').fill("Travel phrases")
    form.locator('textarea[name="text"]').fill(
        "term | meaning | type\nin order to | 为了 | phrase"
    )
    form.get_by_role("button", name="解析预览").click()

    mobile_page.locator("#import-preview").wait_for(state="visible")
    assert mobile_page.locator("#import-summary").get_by_text("1").count() >= 1
    assert mobile_page.get_by_text("in order to", exact=True).is_visible()
    mobile_page.get_by_role("button", name="确认导入").click()

    mobile_page.wait_for_url("**/vocabularies/*")
    assert mobile_page.get_by_role("heading", name="Travel phrases").is_visible()
    entry = mobile_page.locator("article")
    assert entry.get_by_text("in order to", exact=True).is_visible()
    assert entry.get_by_text("搭配", exact=True).is_visible()
    assert _has_horizontal_overflow(mobile_page) is False
    assert _small_visible_controls(mobile_page) == []


def test_csv_upload_import(mobile_page: Page, live_server: str) -> None:
    mobile_page.goto(f"{live_server}/vocabularies/import")
    mobile_page.get_by_role("tab", name="上传文件").click()
    form = mobile_page.locator('form[data-mode="upload"]')
    form.locator('input[name="name"]').fill("Uploaded words")
    form.locator('input[name="file"]').set_input_files(
        {
            "name": "words.csv",
            "mimeType": "text/csv",
            "buffer": b"term,meaning,pos\nfocus,attention,noun",
        }
    )
    form.get_by_role("button", name="解析预览").click()

    mobile_page.locator("#import-preview").wait_for(state="visible")
    assert mobile_page.get_by_text("focus", exact=True).is_visible()
    mobile_page.get_by_role("button", name="确认导入").click()

    mobile_page.wait_for_url("**/vocabularies/*")
    assert mobile_page.get_by_role("heading", name="Uploaded words").is_visible()
    assert mobile_page.locator("article").get_by_text("focus", exact=True).is_visible()
    assert _has_horizontal_overflow(mobile_page) is False


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("E2E server exited before becoming ready")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("E2E server did not become ready")


def _has_horizontal_overflow(page: Page) -> bool:
    return bool(
        page.evaluate(
            "() => document.documentElement.scrollWidth > "
            "document.documentElement.clientWidth"
        )
    )


def _small_visible_controls(page: Page) -> list[float]:
    return page.locator("button, input, select, a").evaluate_all(
        """
        elements => elements
          .map(element => element.getBoundingClientRect())
          .filter(rect => rect.width > 0 && rect.height > 0 && rect.height < 44)
          .map(rect => rect.height)
        """
    )
