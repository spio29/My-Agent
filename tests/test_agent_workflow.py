import asyncio
import pytest
from app.jobs.handlers import agent_workflow

class _FakeHttpTool:
    def __init__(self):
        self.calls = []

    async def run(self, input_data, ctx):
        self.calls.append(input_data)
        return {"success": True, "status": 200, "body": '{"ok":true}'}

class _Ctx:
    def __init__(self, http_tool, command_tool=None, job_id="job_test", run_id="run_test"):
        self.tools = {"http": http_tool}
        if command_tool:
            self.tools["command"] = command_tool
        self.job_id = job_id
        self.run_id = run_id

class _FakeCommandTool:
    def __init__(self):
        self.calls = []

    async def run(self, input_data, ctx):
        self.calls.append(input_data)
        return {
            "success": True,
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 120,
            "workdir": input_data.get("workdir") or ".",
        }

async def _noop_append_event(*args, **kwargs):
    return None

async def _noop_list_approvals(*args, **kwargs):
    return []

def test_agent_workflow_requires_prompt():
    http_tool = _FakeHttpTool()
    result = asyncio.run(agent_workflow.run(_Ctx(http_tool), {}))
    assert result["success"] is False
    assert "prompt" in result["error"]

def test_agent_workflow_executes_provider_and_mcp_steps(monkeypatch):
    async def fake_list_accounts(include_secret: bool = False):
        return [
            {"provider": "openai", "account_id": "default", "enabled": True, "secret": "sk-1"},
            {"provider": "github", "account_id": "default", "enabled": True, "secret": "ghp-1", "config": {"base_url": "https://api.github.com"}},
        ]

    async def fake_list_mcp_servers(include_secret: bool = False):
        return [{"server_id": "mcp_main", "enabled": True, "transport": "http", "url": "https://mcp.example.com"}]

    async def fake_plan_actions_with_openai(*args, **kwargs):
        # Only provide steps if it's the first iteration to test execution
        if kwargs.get("current_iteration", 0) == 0:
            return {
                "summary": "Step 1",
                "steps": [
                    {"kind": "provider_http", "provider": "github", "account_id": "default", "method": "GET", "path": "/user"},
                    {"kind": "mcp_http", "server_id": "mcp_main", "method": "GET", "path": "/health"},   
                ],
                "final_message": "",
            }
        return {"summary": "Done", "steps": [], "final_message": "ok"}

    monkeypatch.setattr(agent_workflow, "list_integration_accounts", fake_list_accounts)
    monkeypatch.setattr(agent_workflow, "list_mcp_servers", fake_list_mcp_servers)
    monkeypatch.setattr(agent_workflow, "_rencanakan_aksi_dengan_openai", fake_plan_actions_with_openai)
    monkeypatch.setattr(agent_workflow, "append_event", _noop_append_event)
    monkeypatch.setattr(agent_workflow, "list_approval_requests", _noop_list_approvals)

    http_tool = _FakeHttpTool()
    result = asyncio.run(agent_workflow.run(_Ctx(http_tool), {"prompt": "cek github dan mcp"}))

    assert result["success"] is True
    assert result["steps_executed"] >= 2
    assert len(http_tool.calls) == 2

def test_agent_workflow_fails_when_openai_key_missing(monkeypatch):
    async def fake_list_accounts(include_secret: bool = False):
        return []

    monkeypatch.setattr(agent_workflow, "list_integration_accounts", fake_list_accounts)
    monkeypatch.setattr(agent_workflow, "append_event", _noop_append_event)
    monkeypatch.setattr(agent_workflow, "list_approval_requests", _noop_list_approvals)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LOCAL_AI_API_KEY", "")

    # Force cloud planner path so missing key returns explicit approval response.
    monkeypatch.setattr(agent_workflow, "OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions")

    async def empty_list(*args, **kwargs):
        return []

    monkeypatch.setattr(agent_workflow, "list_mcp_servers", empty_list)

    http_tool = _FakeHttpTool()
    result = asyncio.run(
        agent_workflow.run(
            _Ctx(http_tool),
            {
                "prompt": "cek github",
                "require_approval_for_missing": True,
                "ai_mode": "cloud",
            },
        )
    )
    assert result["success"] is False
    assert result.get("requires_approval") is True or "API key" in str(result.get("error") or "")

def test_agent_workflow_executes_local_command_step(monkeypatch):
    async def fake_list_accounts(include_secret: bool = False):
        return [{"provider": "openai", "account_id": "default", "enabled": True, "secret": "sk-1"}]

    async def fake_plan_actions_with_openai(*args, **kwargs):
        if kwargs.get("current_iteration", 0) == 0:
            return {
                "summary": "Run command",
                "steps": [{"kind": "local_command", "command": "pytest -q", "workdir": ".", "timeout_sec": 120}],
                "final_message": "",
            }
        return {"summary": "Done", "steps": [], "final_message": "ok"}

    async def empty_list(*args, **kwargs): return []
    monkeypatch.setattr(agent_workflow, "list_integration_accounts", fake_list_accounts)
    monkeypatch.setattr(agent_workflow, "list_mcp_servers", empty_list)
    monkeypatch.setattr(agent_workflow, "_rencanakan_aksi_dengan_openai", fake_plan_actions_with_openai)
    monkeypatch.setattr(agent_workflow, "append_event", _noop_append_event)
    monkeypatch.setattr(agent_workflow, "list_approval_requests", _noop_list_approvals)

    http_tool = _FakeHttpTool()
    command_tool = _FakeCommandTool()
    result = asyncio.run(agent_workflow.run(_Ctx(http_tool, command_tool=command_tool), {"prompt": "tes lokal"}))

    assert result["success"] is True
    assert len(command_tool.calls) == 1

def test_agent_workflow_requests_approval_for_sensitive_command(monkeypatch):
    async def fake_list_accounts(include_secret: bool = False):
        return [{"provider": "openai", "account_id": "default", "enabled": True, "secret": "sk-1"}]

    async def fake_plan_actions_with_openai(*args, **kwargs):
        return {
            "summary": "Sensitive plan",
            "steps": [{"kind": "local_command", "command": "git push origin main"}],
            "final_message": "",
        }

    async def empty_list(*args, **kwargs): return []
    monkeypatch.setattr(agent_workflow, "list_integration_accounts", fake_list_accounts)
    monkeypatch.setattr(agent_workflow, "list_mcp_servers", empty_list)
    monkeypatch.setattr(agent_workflow, "_rencanakan_aksi_dengan_openai", fake_plan_actions_with_openai)
    monkeypatch.setattr(agent_workflow, "append_event", _noop_append_event)
    monkeypatch.setattr(agent_workflow, "list_approval_requests", _noop_list_approvals)

    http_tool = _FakeHttpTool()
    result = asyncio.run(agent_workflow.run(_Ctx(http_tool), {"prompt": "deploy"}))

    assert result["success"] is False
    assert result.get("requires_approval") is True

def test_agent_workflow_uses_prompt_from_experiment_context(monkeypatch):
    async def fake_list_accounts(include_secret: bool = False):
        return [{"provider": "openai", "account_id": "default", "enabled": True, "secret": "sk-1"}]

    async def fake_resolve_experiment_prompt_for_job(*args, **kwargs):
        return {"applied": True, "prompt": "Prompt eksperimen", "experiment_id": "e1", "variant": "b"}

    captured = {"prompt": ""}
    async def fake_plan_actions_with_openai(prompt, *args, **kwargs):
        captured["prompt"] = prompt
        return {"summary": "Plan", "steps": [], "final_message": "ok"}

    async def empty_list(*args, **kwargs): return []
    monkeypatch.setattr(agent_workflow, "list_integration_accounts", fake_list_accounts)
    monkeypatch.setattr(agent_workflow, "list_mcp_servers", empty_list)
    monkeypatch.setattr(agent_workflow, "resolve_experiment_prompt_for_job", fake_resolve_experiment_prompt_for_job)
    monkeypatch.setattr(agent_workflow, "record_experiment_variant_run", lambda *a, **k: None)
    monkeypatch.setattr(agent_workflow, "_rencanakan_aksi_dengan_openai", fake_plan_actions_with_openai)
    monkeypatch.setattr(agent_workflow, "append_event", _noop_append_event)
    monkeypatch.setattr(agent_workflow, "list_approval_requests", _noop_list_approvals)

    http_tool = _FakeHttpTool()
    result = asyncio.run(agent_workflow.run(_Ctx(http_tool), {"prompt": "Asli"}))

    assert result["success"] is True
    assert captured["prompt"] == "Prompt eksperimen"
