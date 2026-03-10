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


def test_settings_surface_drops_legacy_mcp_catalog_and_skill_artifacts() -> None:
    settings_page = _read("ui/src/app/settings/page.tsx")
    api_client = _read("ui/src/lib/api.ts")

    assert "getIntegrationAccounts" not in settings_page
    assert "getIntegrationsCatalog" not in settings_page
    assert "getMcpIntegrationServers" not in settings_page
    assert "Integration inventory" not in settings_page
    assert "Template catalog" not in settings_page
    assert "MCP servers" not in settings_page
    assert "provider template" not in settings_page
    assert "Gagal memuat katalog konektor" not in settings_page
    assert "Gagal memuat daftar MCP server" not in settings_page

    assert "Gagal memuat update skill" not in api_client
    assert "export interface McpIntegrationServer" not in api_client
    assert "export interface IntegrationAccount" not in api_client
    assert "export interface Skill" not in api_client
    assert "export const getMcpIntegrationServers" not in api_client
    assert "export const getIntegrationAccounts" not in api_client
    assert "export const getIntegrationsCatalog" not in api_client
    assert "export const getSkills" not in api_client
