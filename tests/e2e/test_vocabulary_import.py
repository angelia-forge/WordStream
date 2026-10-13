from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Browser, Error, Page, sync_playwright
from sqlalchemy import func, select

from app.config import AuthMode, Environment, Settings
from app.db import create_database_engine, create_session_factory
from app.models.learning import (
    LearningEvent,
    ReviewState,
    SessionItem,
    StudyPlan,
)
from app.models.vocabulary import Entry, Vocabulary


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
            chrome_path = Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            )
            if (
                os.environ.get("RUN_SYSTEM_CHROME_E2E") != "1"
                or not chrome_path.exists()
            ):
                pytest.skip(f"Playwright Chromium is not installed: {exc}")
            browser = playwright.chromium.launch(executable_path=str(chrome_path))
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

    mobile_page.wait_for_url(re.compile(r"/vocabularies/\d+(?:\?.*)?$"))
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

    mobile_page.wait_for_url(re.compile(r"/vocabularies/\d+(?:\?.*)?$"))
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
    mobile_page.wait_for_url(re.compile(r"/vocabularies/\d+(?:\?.*)?$"))

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


def test_mobile_study_player_full_flow(
    mobile_page: Page,
    live_server: str,
    e2e_database_url: str,
) -> None:
    mobile_page.add_init_script(_speech_mock("ready"))
    mobile_page.goto(f"{live_server}/vocabularies/import")
    form = mobile_page.locator('form[data-mode="paste"]')
    form.locator('input[name="name"]').fill("Player workflow")
    form.locator('textarea[name="text"]').fill(
        "term|meaning|pos|phonetic|example\n"
        "alpha|一|noun|/a/|alpha example\n"
        "bravo|二|noun|/b/|bravo example\n"
        "charlie|三|noun|/c/|charlie example\n"
        "delta|四|noun|/d/|delta example\n"
        "echo|五|noun|/e/|echo example"
    )
    form.get_by_role("button", name="解析预览").click()
    mobile_page.locator("#import-preview").wait_for(state="visible")
    mobile_page.get_by_role("button", name="确认导入").click()
    mobile_page.wait_for_url(re.compile(r"/vocabularies/\d+(?:\?.*)?$"))
    vocabulary_id = int(urlparse(mobile_page.url).path.rsplit("/", 1)[-1])

    mobile_page.get_by_role("link", name="配置陪读计划").click()
    mobile_page.get_by_label("每日新词数").fill("5")
    mobile_page.get_by_label("每日复习数").fill("0")
    mobile_page.get_by_label("自动切换间隔").fill("1")
    mobile_page.get_by_role("button", name="保存计划").click()
    mobile_page.wait_for_url("**?plan_saved=1")
    mobile_page.get_by_role("button", name="开始陪读").click()
    mobile_page.wait_for_url("**/study/*")
    session_id = int(mobile_page.url.rsplit("/", maxsplit=1)[-1])

    term = mobile_page.locator("[data-study-term]")
    assert term.text_content() == "alpha"
    mobile_page.wait_for_function(
        "() => document.querySelector('[data-study-term]').textContent === 'bravo'"
    )
    mobile_page.get_by_role("button", name="暂停").click()
    paused_term = term.text_content()
    mobile_page.wait_for_timeout(1_200)
    assert term.text_content() == paused_term

    mobile_page.get_by_role("button", name="继续").click()
    mobile_page.wait_for_function(
        "(previous) => document.querySelector('[data-study-term]').textContent "
        "!== previous",
        arg=paused_term,
    )
    mobile_page.get_by_role("button", name="暂停").click()
    retry_term = term.text_content()
    mobile_page.get_by_role("button", name="重来").click()
    assert term.text_content() != retry_term
    mobile_page.get_by_role("button", name="下一个").click()
    assert term.text_content() != retry_term
    mobile_page.get_by_role("button", name="下一个").click()
    assert term.text_content() == retry_term

    mobile_page.get_by_role("button", name="结束").click()
    mobile_page.wait_for_url("**?study_finished=1")
    assert mobile_page.get_by_text("本次陪读已结束").is_visible()
    assert _has_horizontal_overflow(mobile_page) is False
    assert _small_visible_controls(mobile_page) == []

    engine = create_database_engine(
        Settings(
            environment=Environment.TEST,
            auth_mode=AuthMode.DISABLED,
            database_url=e2e_database_url,
        )
    )
    try:
        with create_session_factory(engine)() as session:
            item_ids = select(SessionItem.id).where(
                SessionItem.session_id == session_id
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(LearningEvent)
                    .where(LearningEvent.session_item_id.in_(item_ids))
                )
                == 5
            )
            assert session.scalar(select(func.count()).select_from(ReviewState)) >= 5
    finally:
        engine.dispose()

    mobile_page.goto(f"{live_server}/statistics")
    mobile_page.get_by_label("词库").select_option(str(vocabulary_id))
    mobile_page.get_by_role("button", name="筛选").click()
    mobile_page.wait_for_url(f"**/statistics?vocabulary_id={vocabulary_id}")
    assert (
        mobile_page.locator("article", has_text="今日已学")
        .get_by_text("5", exact=True)
        .is_visible()
    )


def test_offline_outbox_retries_when_network_returns(
    browser: Browser,
    live_server: str,
    e2e_database_url: str,
) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.add_init_script(_speech_mock("ready"))
        session_id = _seed_player_session(
            page,
            live_server,
            e2e_database_url,
            name="Offline outbox",
            interval_seconds=10,
            count=2,
        )
        endpoint = f"**/api/v1/study-sessions/{session_id}/outcomes/batch"
        page.route(endpoint, lambda route: route.abort())
        page.goto(f"{live_server}/study/{session_id}")
        page.get_by_role("button", name="下一个").click()
        page.get_by_role("button", name="暂停").click()
        page.get_by_text("学习进度同步失败").wait_for(timeout=5_000)
        assert (
            page.evaluate(
                "(id) => JSON.parse(localStorage.getItem("
                "`wordstream.study.outbox.${id}`)).length",
                session_id,
            )
            == 1
        )

        page.unroute(endpoint)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        page.wait_for_function(
            "(id) => localStorage.getItem(" "`wordstream.study.outbox.${id}`) === null",
            arg=session_id,
        )
        state = page.request.get(f"{live_server}/api/v1/study-sessions/{session_id}")
        assert state.ok
        assert state.json()["items"][0]["result"] == "seen"
    finally:
        page.close()


def test_speech_failures_do_not_stop_automatic_progress(
    browser: Browser,
    live_server: str,
    e2e_database_url: str,
) -> None:
    for mode, expected_status in [
        ("absent", "静默模式"),
        ("empty", "静默模式"),
        ("delayed", "朗读模式"),
        ("throw", "静默模式"),
    ]:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.add_init_script(_speech_mock(mode))
            session_id = _seed_player_session(
                page,
                live_server,
                e2e_database_url,
                name=f"Speech {mode}",
                interval_seconds=1,
            )
            page.goto(f"{live_server}/study/{session_id}")
            first = page.locator("[data-study-term]").text_content()
            page.get_by_text(expected_status, exact=True).wait_for(timeout=2_000)
            page.wait_for_function(
                "(previous) => document.querySelector('[data-study-term]').textContent "
                "!== previous",
                arg=first,
                timeout=2_500,
            )
            page.get_by_role("button", name="暂停").click()
            page.get_by_role("button", name="结束").click()
            page.wait_for_url("**?study_finished=1")
        finally:
            page.close()


def test_visibility_restore_advances_only_one_item(
    browser: Browser,
    live_server: str,
    e2e_database_url: str,
) -> None:
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.add_init_script(_speech_mock("ready"))
        session_id = _seed_player_session(
            page,
            live_server,
            e2e_database_url,
            name="Visibility timing",
            interval_seconds=1,
            count=4,
        )
        page.goto(f"{live_server}/study/{session_id}")
        page.evaluate(
            """
            () => {
              window.__testHidden = true;
              Object.defineProperty(document, "hidden", {
                configurable: true,
                get: () => window.__testHidden,
              });
              document.dispatchEvent(new Event("visibilitychange"));
            }
            """
        )
        page.wait_for_timeout(1_300)
        page.evaluate(
            """
            () => {
              window.__testHidden = false;
              document.dispatchEvent(new Event("visibilitychange"));
            }
            """
        )
        page.wait_for_timeout(150)
        assert page.locator("[data-study-term]").text_content() == "term-1"
        page.get_by_role("button", name="暂停").click()
        page.get_by_role("button", name="结束").click()
        page.wait_for_url("**?study_finished=1")
    finally:
        page.close()


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
    mobile_page.wait_for_url(re.compile(r"/vocabularies/\d+(?:\?.*)?$"))
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
                    client_event_id=str(uuid4()),
                    entry_id=entry.id,
                    term_key=entry.normalized_term,
                    term_snapshot=entry.term,
                    vocabulary_snapshot={
                        "id": vocabulary_id,
                        "name": "Retained history",
                    },
                    result="seen",
                    attempt_count=1,
                    client_attempt_count=1,
                    occurred_at=datetime.now(UTC),
                    timezone=config.app_timezone,
                    activity_date=local_today,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    today_statistics = mobile_page.request.get(
        f"{live_server}/api/v1/statistics/today"
    ).json()
    expected_learned = today_statistics["learned_terms"]
    expected_entries = today_statistics["total_entries"]
    expected_event_total = mobile_page.request.get(
        f"{live_server}/api/v1/statistics"
    ).json()["total_events"]
    mobile_page.goto(f"{live_server}/statistics")
    statistics = mobile_page.locator("article", has_text="今日已学")
    assert statistics.get_by_text(str(expected_learned), exact=True).is_visible()
    assert (
        mobile_page.locator("article", has_text="连续学习天数")
        .get_by_text("1", exact=True)
        .is_visible()
    )
    assert mobile_page.get_by_label("词库").is_visible()

    mobile_page.goto(f"{live_server}/vocabularies")
    card = mobile_page.locator("article", has_text="Retained history")
    card.get_by_role("button", name="删除 Retained history").click()
    dialog = mobile_page.get_by_role("dialog")
    assert dialog.is_visible()
    with mobile_page.expect_response(
        lambda response: response.request.method == "DELETE"
        and f"/api/v1/vocabularies/{vocabulary_id}" in response.url
    ) as deletion:
        dialog.get_by_role("button", name="确认删除").click()
    assert deletion.value.status == 204

    mobile_page.goto(f"{live_server}/statistics")
    statistics = mobile_page.locator("article", has_text="今日已学")
    assert statistics.get_by_text(str(expected_learned), exact=True).is_visible()
    assert (
        mobile_page.locator("article", has_text="连续学习天数")
        .get_by_text("1", exact=True)
        .is_visible()
    )
    assert (
        mobile_page.locator("article", has_text="总词条数")
        .get_by_text(str(expected_entries - 1), exact=True)
        .is_visible()
    )
    assert _has_horizontal_overflow(mobile_page) is False
    assert _small_visible_controls(mobile_page) == []

    engine = create_database_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(LearningEvent))
                == expected_event_total
            )
            event = next(
                (
                    candidate
                    for candidate in session.scalars(select(LearningEvent))
                    if candidate.vocabulary_snapshot["name"] == "Retained history"
                ),
                None,
            )
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


def _seed_player_session(
    page: Page,
    base_url: str,
    database_url: str,
    *,
    name: str,
    interval_seconds: int,
    count: int = 3,
) -> int:
    config = Settings(
        environment=Environment.TEST,
        auth_mode=AuthMode.DISABLED,
        database_url=database_url,
    )
    engine = create_database_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            vocabulary = Vocabulary(name=name, entry_count=count)
            session.add(vocabulary)
            session.flush()
            session.add_all(
                [
                    Entry(
                        vocabulary_id=vocabulary.id,
                        term=f"term-{index}",
                        normalized_term=f"term-{index}",
                        entry_type="word",
                        meaning=f"meaning-{index}",
                        tags=[],
                    )
                    for index in range(count)
                ]
            )
            session.add(
                StudyPlan(
                    vocabulary_id=vocabulary.id,
                    daily_new_count=count,
                    daily_review_count=0,
                    interval_seconds=interval_seconds,
                )
            )
            session.commit()
            vocabulary_id = vocabulary.id
    finally:
        engine.dispose()

    response = page.request.post(
        f"{base_url}/api/v1/study-sessions",
        data={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert response.ok
    return int(response.json()["session"]["id"])


def _speech_mock(mode: str) -> str:
    if mode == "absent":
        return """
          Object.defineProperty(window, "speechSynthesis", {
            configurable: true,
            value: undefined,
          });
          Object.defineProperty(window, "SpeechSynthesisUtterance", {
            configurable: true,
            value: undefined,
          });
        """

    voices = "[]" if mode in {"empty", "delayed"} else "[{ lang: 'en-US' }]"
    speak = (
        "throw new Error('speak failed');"
        if mode == "throw"
        else """
      window.__spoken.push(utterance.text);
    """
    )
    delayed = ""
    if mode == "delayed":
        delayed = """
          setTimeout(() => {
            window.__voices = [{ lang: "en-US" }];
            if (window.__voicesChanged) window.__voicesChanged();
          }, 100);
        """
    return f"""
      window.__spoken = [];
      window.__voices = {voices};
      window.SpeechSynthesisUtterance = class {{
        constructor(text) {{
          this.text = text;
          this.lang = "";
          this.rate = 1;
          this.voice = null;
        }}
      }};
      Object.defineProperty(window, "speechSynthesis", {{
        configurable: true,
        value: {{
          getVoices: () => window.__voices,
          addEventListener: (name, callback) => {{
            if (name === "voiceschanged") window.__voicesChanged = callback;
          }},
          speak: (utterance) => {{ {speak} }},
          cancel: () => {{}},
          pause: () => {{}},
          resume: () => {{}},
        }},
      }});
      {delayed}
    """
