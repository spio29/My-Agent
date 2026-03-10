from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_operator_ui_cleanup_removes_legacy_dashboard_and_preview_surface() -> None:
    compose = _read("docker-compose.yml")
    prod_compose = _read("docker-compose.prod.yml")
    watchdog = _read("ops/no-code/watchdog.py")
    next_config = _read("ui/next.config.js")
    sidebar_nav = _read("ui/src/components/sidebar-nav.tsx")
    api_client = _read("ui/src/lib/api.ts")

    assert "spio-dashboard" not in compose
    assert "spio-dashboard" not in prod_compose
    assert "spio-dashboard" not in watchdog

    assert "3001:3000" not in compose
    assert '"3001:3000"' not in prod_compose
    assert "5178:3000" in compose
    assert '"5178:3000"' in prod_compose
    assert "spio-operator-ui" in compose
    assert "spio-operator-ui" in prod_compose

    assert "NEXT_PUBLIC_BASE_PATH" not in next_config
    assert "NEXT_PUBLIC_BASE_PATH" not in sidebar_nav
    assert "NEXT_PUBLIC_BASE_PATH" not in api_client
    assert "multi-influencer-preview" not in next_config
    assert "multi-influencer-preview" not in sidebar_nav
    assert "multi-influencer-preview" not in api_client

    assert not (ROOT / "ui-simple").exists()
    assert not (ROOT / "docs" / "README_UI_SIMPLE.md").exists()
    assert not (ROOT / "docs" / "UI_AUTO_UPDATE_AND_AGENT_247.md").exists()
