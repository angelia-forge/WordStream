from fastapi.testclient import TestClient


def import_text(client: TestClient, name: str, text: str) -> int:
    preview = client.post(
        "/api/v1/vocabularies/import/preview",
        data={"name": name, "text": text, "duplicate_policy": "skip"},
    )
    assert preview.status_code == 200
    imported = client.post(
        "/api/v1/vocabularies/import",
        data={
            "name": name,
            "text": text,
            "duplicate_policy": "skip",
            "preview_digest": preview.json()["preview_digest"],
        },
    )
    assert imported.status_code == 201
    return int(imported.json()["vocabulary_id"])


def test_development_shell_is_rendered(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "WordStream" in response.text
    assert 'rel="manifest"' in response.text


def test_password_login_opens_protected_shell(
    protected_client: TestClient,
) -> None:
    login_page = protected_client.get("/")

    assert login_page.status_code == 200
    assert login_page.url.path == "/login"
    assert 'name="password"' in login_page.text

    logged_in = protected_client.post(
        "/login",
        data={"password": "correct-password"},
    )

    assert logged_in.status_code == 200
    assert logged_in.url.path == "/"
    assert 'name="csrf_token"' in logged_in.text


def test_service_worker_is_available(client: TestClient) -> None:
    response = client.get("/service-worker.js")

    assert response.status_code == 200
    assert response.headers["service-worker-allowed"] == "/"


def test_vocabulary_list_supports_search_and_delete_entry(
    client: TestClient,
) -> None:
    import_text(client, "Travel phrases", "term|meaning\ncheck in|登记")
    import_text(client, "Work words", "term|meaning\nfocus|专注")

    response = client.get("/vocabularies", params={"q": "Travel"})

    assert response.status_code == 200
    assert "Travel phrases" in response.text
    assert "Work words" not in response.text
    assert "data-delete-trigger" in response.text
    assert 'data-redirect-url="/vocabularies"' in response.text


def test_vocabulary_detail_supports_filters_sort_and_pagination(
    client: TestClient,
) -> None:
    rows = ["term|meaning|tags"]
    rows.extend(
        f"term-{index:02d}|meaning-{index}|{'focus' if index < 2 else 'other'}"
        for index in range(21)
    )
    vocabulary_id = import_text(client, "Paged words", "\n".join(rows))

    filtered = client.get(
        f"/vocabularies/{vocabulary_id}",
        params={
            "q": "term-0",
            "tag": "focus",
            "sort": "created_at",
            "order": "desc",
        },
    )
    assert filtered.status_code == 200
    assert "找到 2 个词条" in filtered.text
    assert "term-00" in filtered.text
    assert "term-01" in filtered.text
    assert 'option value="focus" selected' in filtered.text

    first_page = client.get(f"/vocabularies/{vocabulary_id}")
    assert first_page.status_code == 200
    assert "找到 21 个词条" in first_page.text
    assert "下一页" in first_page.text
    second_page = client.get(f"/vocabularies/{vocabulary_id}", params={"page": 2})
    assert second_page.status_code == 200
    assert "term-20" in second_page.text
    assert "上一页" in second_page.text


def test_statistics_page_renders_retained_metrics(client: TestClient) -> None:
    response = client.get("/statistics")

    assert response.status_code == 200
    assert "今日已学" in response.text
    assert "今日待复习" in response.text
    assert "连续学习天数" in response.text
    assert "总词条数" in response.text
    assert "全部词库" in response.text


def test_plan_page_and_configured_detail_are_rendered(
    client: TestClient,
) -> None:
    vocabulary_id = import_text(
        client,
        "Plan words",
        "term|meaning\nfocus|attention",
    )

    page = client.get(f"/vocabularies/{vocabulary_id}/plan")
    assert page.status_code == 200
    assert "data-plan-form" in page.text
    assert page.text.count('inputmode="numeric"') == 3
    assert 'name="interval_seconds"' in page.text

    saved = client.put(
        f"/api/v1/vocabularies/{vocabulary_id}/plan",
        json={
            "daily_new_count": 10,
            "daily_review_count": 15,
            "interval_seconds": 3,
            "is_random": True,
            "is_loop": False,
        },
    )
    assert saved.status_code == 200

    detail = client.get(
        f"/vocabularies/{vocabulary_id}",
        params={"plan_saved": "true"},
    )
    assert detail.status_code == 200
    assert "陪读计划已保存" in detail.text
    assert "开始陪读" in detail.text
    assert "data-start-study" in detail.text
    assert "编辑计划" in detail.text

    created = client.post(
        "/api/v1/study-sessions",
        json={"vocabulary_id": vocabulary_id, "resume_existing": True},
    )
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]

    player = client.get(f"/study/{session_id}")
    assert player.status_code == 200
    assert "data-study-player" in player.text
    assert "/static/js/study-player.js" in player.text
    assert "focus" in player.text
