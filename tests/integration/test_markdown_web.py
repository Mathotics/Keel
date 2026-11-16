from fastapi.testclient import TestClient


def test_markdown_fields_share_one_editor(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"key": "KEEL", "name": "Keel"},
    ).json()
    issue = client.post(
        f"/api/v1/projects/{created['id']}/issues",
        json={"type": "story", "title": "Paint the door"},
    ).json()

    create = client.get("/create?project=KEEL")
    assert create.status_code == 200
    assert 'id="issue-title"' in create.text
    assert "data-keel-markdown" not in create.text.split('id="issue-title"')[0]
    assert create.text.count("data-keel-markdown") == 2
    assert "Markdown is supported." in create.text
    assert "keel-md__save" not in create.text
    assert 'name="description"' in create.text
    assert 'name="definition_of_done"' in create.text
    assert "/assets/js/markdown-field.js" in create.text

    page = client.get(f"/issues/{issue['key']}")
    assert page.text.count("data-keel-markdown") == 3
    assert 'name="body"' in page.text
    assert "Add your comment here…" in page.text
    assert page.text.count('aria-label="Cancel"') == 3
    assert page.text.count("keel-md__save") == 3
    assert 'aria-label="Add comment"' in page.text
    assert ">Add comment<" not in page.text
    description = page.text.split("/description", 1)[1].split("</form>", 1)[0]
    assert "data-keel-autosubmit" not in description
    assert 'name="title"' in page.text
    title = page.text.split('name="title"', 1)[1][:80]
    assert "data-keel-markdown" not in title


def test_preview_uses_the_saved_renderer(client: TestClient) -> None:
    response = client.post(
        "/web/markdown/preview",
        data={"body": "A **bold** note.\n\n<script>alert(1)</script>"},
    )
    assert response.status_code == 200
    assert response.headers["x-keel-markdown"] == "preview"
    assert "<strong>bold</strong>" in response.text
    assert "<script>" not in response.text

    empty = client.post("/web/markdown/preview", data={"body": "  "})
    assert "Nothing to preview." in empty.text


def test_preview_asks_the_visitor_to_sign_in(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        "/web/markdown/preview",
        data={"body": "Hello"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")
