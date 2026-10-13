from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Browser, Error, Page, sync_playwright
from sqlalchemy import func, select

from app.config import AuthMode, Environment, Settings
from app.db import create_database_engine, create_session_factory
from app.models.learning import LearningEvent, ReviewState, StudyPlan
from app.models.vocabulary import Entry


@pytest.fixture(scope="module")
def e2e_database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    database_path = tmp_path_factory.mktemp("e2e") / "wordstream.db"
    database_url = f"sqlite:///{database_path}"
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
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
    return database_url


@pytest.fixture(scope="module")
def live_server(e2e_database_url: str) -> Iterator[str]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "DATABASE_URL": e2e_database_url,
        "ENVIRONMENT": "test",
        "AUTH_MODE": "disabled",
    }
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


def test_mobile_configures_and_saves_study_plan(
    mobile_page: Page,
    live_server: str,
) -> None:
    mobile_page.goto(f"{live_server}/vocabularies/import")
    form = mobile_page.locator('form[data-mode="paste"]')
    form.locator('input[name="name"]').fill("Plan vocabulary")
    form.locator('textarea[name="text"]').fill("term|meaning\nfocus|专注")
    form.get_by_role("button", name="解析预览").click()
    mobile_page.locator("#import-preview").wait_for(state="visible")
    mobile_page.get_by_role("button", name="确认导入").click()
    mobile_page.wait_for_url("**/vocabularies/*")

    mobile_page.get_by_role("link", name="配置陪读计划").click()
    mobile_page.wait_for_url("**/plan")
    mobile_page.get_by_label("每日新词数").fill("0")
    mobile_page.get_by_label("每日复习数").fill("25")
    mobile_page.get_by_label("自动切换间隔").fill("7")
    mobile_page.get_by_label("随机播放").check()
    mobile_page.get_by_label("循环播放").check()
    mobile_page.get_by_role("button", name="保存计划").click()

    mobile_page.wait_for_url("**?plan_saved=1")
    assert mobile_page.get_by_text("陪读计划已保存").is_visible()
    assert mobile_page.get_by_role("button", name="开始陪读").is_visible()
    assert mobile_page.get_by_role("link", name="编辑计划").is_visible()
    assert _has_horizontal_overflow(mobile_page) is False


def test_mobile_delete_retains_history_statistics(
    mobile_page: Page,
    live_server: str,
    e2e_database_url: str,
) -> None:
    mobile_page.goto(f"{live_server}/vocabularies/import")
    form = mobile_page.locator('form[data-mode="paste"]')
    form.locator('input[name="name"]').fill("Retained history")
    form.locator('textarea[name="text"]').fill("term|meaning\nfocus|专注")
    form.get_by_role("button", name="解析预览").click()
    mobile_page.locator("#import-preview").wait_for(state="visible")
    mobile_page.get_by_role("button", name="确认导入").click()
    mobile_page.wait_for_url("**/vocabularies/*")
    vocabulary_id = int(urlparse(mobile_page.url).path.rsplit("/", 1)[-1])

    config = Settings(
        environment=Environment.TEST,
        auth_mode=AuthMode.DISABLED,
        database_url=e2e_database_url,
    )
    engine = create_database_engine(config)
    session_factory = create_session_factory(engine)
    local_today = datetime.now(ZoneInfo(config.app_timezone)).date()
    try:
        with session_factory() as session:
            entry = session.scalar(
                select(Entry).where(Entry.vocabulary_id == vocabulary_id)
            )
            assert entry is not None
            session.add(StudyPlan(vocabulary_id=vocabulary_id))
            session.add(ReviewState(entry_id=entry.id))
            session.add(
                LearningEvent(
                    entry_id=entry.id,
                    term_key=entry.normalized_term,
                    term_snapshot=entry.term,
                    vocabulary_id_snapshot=vocabulary_id,
                    vocabulary_name_snapshot="Retained history",
                    result="remembered",
                    attempts=1,
                    occurred_at=datetime.now(UTC),
                    timezone=config.app_timezone,
                    activity_date=local_today,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    mobile_page.goto(f"{live_server}/statistics")
    assert (
        mobile_page.get_by_text("学习记录").locator("..").get_by_text("1").is_visible()
    )
    assert (
        mobile_page.get_by_text("连续学习天数")
        .locator("..")
        .get_by_text("1")
        .is_visible()
    )

    mobile_page.goto(f"{live_server}/vocabularies")
    card = mobile_page.locator("article", has_text="Retained history")
    card.get_by_role("button", name="删除 Retained history").click()
    dialog = mobile_page.get_by_role("dialog")
    assert dialog.is_visible()
    dialog.get_by_role("button", name="确认删除").click()
    mobile_page.wait_for_url(f"{live_server}/vocabularies")

    mobile_page.goto(f"{live_server}/statistics")
    assert (
        mobile_page.get_by_text("学习记录").locator("..").get_by_text("1").is_visible()
    )
    assert (
        mobile_page.get_by_text("连续学习天数")
        .locator("..")
        .get_by_text("1")
        .is_visible()
    )
    assert _has_horizontal_overflow(mobile_page) is False
    assert _small_visible_controls(mobile_page) == []

    engine = create_database_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(LearningEvent)) == 1
            event = session.scalar(select(LearningEvent))
            assert event is not None
            assert event.entry_id is None
    finally:
        engine.dispose()


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
