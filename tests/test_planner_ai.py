import asyncio
import time

from app.services.api import planner_ai
from app.services.api.planner_ai import (
    PlannerAiRequest,
    build_plan_from_ai_payload,
    build_plan_with_ai,
    resolve_planner_ai_credential_candidates,
    resolve_planner_ai_credentials,
)


def test_build_plan_from_ai_payload_converts_jobs():
    request = PlannerAiRequest(
        prompt="monitor dan laporan",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "jobs": [
            {
                "job_id": "monitor-utama",
                "type": "monitor.channel",
                "reason": "Pantau koneksi utama",
                "schedule": {"interval_sec": 60},
                "inputs": {"channel": "whatsapp", "account_id": "ops_01"},
            },
            {
                "type": "report.daily",
                "reason": "Laporan harian",
                "schedule": {"cron": "0 7 * * *"},
                "inputs": {"timezone": "Asia/Jakarta"},
            },
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert plan.planner_source == "smolagents"
    assert len(plan.jobs) == 2
    assert plan.jobs[0].job_spec.type == "monitor.channel"
    assert plan.jobs[0].job_spec.inputs["channel"] == "whatsapp"
    assert plan.jobs[1].job_spec.type == "report.daily"
    assert plan.jobs[1].job_spec.schedule is not None
    assert plan.jobs[1].job_spec.schedule.cron == "0 7 * * *"


def test_build_plan_with_ai_force_rule_based_always_uses_fallback():
    request = PlannerAiRequest(
        prompt="Pantau telegram akun bot_a01 tiap 30 detik",
        force_rule_based=True,
    )

    plan = build_plan_with_ai(request)
    assert plan.planner_source == "rule_based"
    assert len(plan.jobs) == 1
    assert any("force_rule_based" in warning for warning in plan.warnings)


def test_build_plan_from_ai_payload_supports_agent_workflow_type():
    request = PlannerAiRequest(
        prompt="Sinkron github ke notion",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Workflow lintas integrasi",
        "jobs": [
            {
                "job_id": "workflow-utama",
                "type": "agent.workflow",
                "reason": "Perlu rangkaian aksi provider",
                "schedule": None,
                "inputs": {"prompt": "Sinkron github ke notion"},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert len(plan.jobs) == 1
    job = plan.jobs[0].job_spec
    assert job.type == "agent.workflow"
    assert job.schedule is None
    assert job.inputs["prompt"] == "Sinkron github ke notion"


def test_build_plan_from_ai_payload_uses_default_schedule_without_warning_when_null():
    request = PlannerAiRequest(
        prompt="monitor dan laporan",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": None,
                "inputs": {},
            },
            {
                "type": "report.daily",
                "reason": "Laporan harian",
                "schedule": None,
                "inputs": {},
            },
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert len(plan.jobs) == 2
    assert not any("schedule tidak valid" in warning for warning in plan.warnings)
    assert plan.jobs[0].job_spec.schedule is not None
    assert plan.jobs[0].job_spec.schedule.interval_sec == 30
    assert plan.jobs[1].job_spec.schedule is not None
    assert plan.jobs[1].job_spec.schedule.cron == "0 7 * * *"


def test_build_plan_from_ai_payload_parses_human_readable_schedule_string():
    request = PlannerAiRequest(
        prompt="monitor dan laporan",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": "setiap 45 detik",
                "inputs": {},
            },
            {
                "type": "report.daily",
                "reason": "Laporan harian",
                "schedule": "harian jam 08:30",
                "inputs": {},
            },
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert len(plan.jobs) == 2
    assert plan.jobs[0].job_spec.schedule is not None
    assert plan.jobs[0].job_spec.schedule.interval_sec == 45
    assert plan.jobs[1].job_spec.schedule is not None
    assert plan.jobs[1].job_spec.schedule.cron == "30 8 * * *"
    assert not any("format schedule string tidak dikenali" in warning for warning in plan.warnings)


def test_build_plan_from_ai_payload_filters_low_signal_messages():
    request = PlannerAiRequest(
        prompt="test planner ai lokal",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "assumptions": [
            "The local environment is set up.",
            "The AI Planner has access to the necessary libraries.",
            "Asumsi bisnis penting",
        ],
        "warnings": [
            "The AI Planner is running locally.",
            "The AI Planner is set up for local use.",
            "Warning penting",
        ],
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": None,
                "warnings": ["The AI Planner is ready for execution."],
                "inputs": {},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert plan.jobs
    assert "Asumsi bisnis penting" in plan.assumptions
    assert "Warning penting" in plan.warnings
    assert not any("AI Planner is running locally" in item for item in plan.warnings)
    assert not any("local environment is set up" in item.lower() for item in plan.assumptions)


def test_build_plan_from_ai_payload_enriches_missing_intent_jobs():
    request = PlannerAiRequest(
        prompt="pantau telegram tiap 30 detik dan kirim report harian jam 08:00",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": {"interval_sec": 30},
                "inputs": {"channel": "telegram", "account_id": "bot_a01"},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)
    job_types = [job.job_spec.type for job in plan.jobs]

    assert "monitor.channel" in job_types
    assert "report.daily" in job_types
    assert not any("melengkapi output AI" in warning for warning in plan.warnings)


def test_build_plan_from_ai_payload_no_warning_for_common_type_alias():
    request = PlannerAiRequest(
        prompt="monitor telegram",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "jobs": [
            {
                "type": "monitor",
                "reason": "Pantau channel",
                "schedule": {"interval_sec": 30},
                "inputs": {},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert len(plan.jobs) == 1
    assert plan.jobs[0].job_spec.type == "monitor.channel"
    assert not any("dinormalisasi menjadi" in warning for warning in plan.warnings)


def test_build_plan_from_ai_payload_localizes_business_warnings_to_indonesian():
    request = PlannerAiRequest(
        prompt="monitor telegram",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "warnings": [
            "Ensure the user has the necessary permissions to send reports.",
            "Telegram is running and accessible.",
        ],
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": None,
                "inputs": {},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)

    assert any("Pastikan pengguna memiliki izin untuk mengirim laporan." in item for item in plan.warnings)
    assert any("Telegram aktif dan dapat diakses." in item for item in plan.warnings)
    assert not any("Ensure the user has the necessary permissions to send reports." in item for item in plan.warnings)


def test_build_plan_from_ai_payload_localizes_verify_api_key_message():
    request = PlannerAiRequest(
        prompt="monitor telegram",
        timezone="Asia/Jakarta",
        default_channel="telegram",
        default_account_id="bot_a01",
    )

    payload = {
        "summary": "Rencana dari AI",
        "warnings": ["Verify the API key is valid and accessible."],
        "jobs": [
            {
                "type": "monitor.channel",
                "reason": "Pantau channel",
                "schedule": None,
                "inputs": {},
            }
        ],
    }

    plan = build_plan_from_ai_payload(request, payload)
    assert any("Pastikan kunci API valid dan dapat diakses." in item for item in plan.warnings)


def test_resolve_planner_ai_credentials_uses_dashboard_account(monkeypatch):
    async def fake_get_integration_account(provider: str, account_id: str, include_secret: bool = False):
        assert provider == "openai"
        assert account_id == "default"
        return {
            "provider": "openai",
            "account_id": "default",
            "enabled": True,
            "secret": "sk-dashboard",
            "config": {"model_id": "openai/gpt-4.1-mini"},
        }

    async def fake_list_integration_accounts(provider=None, include_secret=False):
        raise AssertionError("list_integration_accounts should not be called when preferred account is ready")

    monkeypatch.setattr(planner_ai, "get_integration_account", fake_get_integration_account)
    monkeypatch.setattr(planner_ai, "list_integration_accounts", fake_list_integration_accounts)
    monkeypatch.delenv("PLANNER_AI_PROVIDER_CHAIN", raising=False)

    request = PlannerAiRequest(prompt="uji", openai_account_id="default")
    model_id, api_key, warnings = asyncio.run(resolve_planner_ai_credentials(request))

    assert model_id == "openai/gpt-4.1-mini"
    assert api_key == "sk-dashboard"
    assert warnings == []


def test_resolve_planner_ai_credentials_falls_back_to_env(monkeypatch):
    async def fake_get_integration_account(provider: str, account_id: str, include_secret: bool = False):
        return None

    async def fake_list_integration_accounts(provider=None, include_secret=False):
        return []

    monkeypatch.setattr(planner_ai, "get_integration_account", fake_get_integration_account)
    monkeypatch.setattr(planner_ai, "list_integration_accounts", fake_list_integration_accounts)
    monkeypatch.delenv("PLANNER_AI_PROVIDER_CHAIN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("PLANNER_AI_MODEL", "openai/gpt-4o-mini")

    request = PlannerAiRequest(prompt="uji", openai_account_id="default")
    model_id, api_key, warnings = asyncio.run(resolve_planner_ai_credentials(request))

    assert model_id == "openai/gpt-4o-mini"
    assert api_key == "sk-env"
    assert any("OPENAI_API_KEY" in item for item in warnings)


def test_resolve_planner_ai_credentials_can_select_ollama_provider(monkeypatch):
    async def fake_get_integration_account(provider: str, account_id: str, include_secret: bool = False):
        if provider != "ollama":
            return None
        return {
            "provider": "ollama",
            "account_id": "default",
            "enabled": True,
            "secret": "",
            "config": {"model_id": "qwen3:8b", "base_url": "http://localhost:11434/v1"},
        }

    async def fake_list_integration_accounts(provider=None, include_secret=False):
        return []

    monkeypatch.setattr(planner_ai, "get_integration_account", fake_get_integration_account)
    monkeypatch.setattr(planner_ai, "list_integration_accounts", fake_list_integration_accounts)

    request = PlannerAiRequest(prompt="uji", ai_provider="ollama", ai_account_id="default")
    model_id, api_key, warnings = asyncio.run(resolve_planner_ai_credentials(request))

    assert model_id == "ollama/qwen3:8b"
    assert api_key
    assert warnings == []


def test_resolve_planner_ai_candidates_auto_falls_back_to_ollama(monkeypatch):
    async def fake_get_integration_account(provider: str, account_id: str, include_secret: bool = False):
        if provider == "openai":
            return None
        if provider == "ollama":
            return {
                "provider": "ollama",
                "account_id": "default",
                "enabled": True,
                "secret": "",
                "config": {"model_id": "qwen3:8b", "base_url": "http://localhost:11434/v1"},
            }
        return None

    async def fake_list_integration_accounts(provider=None, include_secret=False):
        return []

    monkeypatch.setattr(planner_ai, "get_integration_account", fake_get_integration_account)
    monkeypatch.setattr(planner_ai, "list_integration_accounts", fake_list_integration_accounts)
    monkeypatch.delenv("PLANNER_AI_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    request = PlannerAiRequest(prompt="uji", ai_provider="auto", ai_account_id="default")
    kandidat, warnings = asyncio.run(resolve_planner_ai_credential_candidates(request))

    assert kandidat
    assert kandidat[0].provider == "ollama"
    assert kandidat[0].model_id.startswith("ollama/")
    assert any("OpenAI" in item for item in warnings)



def _reset_planner_ai_limiter_state() -> None:
    planner_ai._PLANNER_AI_SEMAPHORE = None
    planner_ai._PLANNER_AI_SEMAPHORE_SIZE = 0


def test_build_plan_with_ai_falls_back_when_planner_busy(monkeypatch):
    async def fake_resolve_candidates(_request):
        return [
            planner_ai.PlannerAiCredentials(
                provider="ollama",
                account_id="default",
                model_id="ollama/qwen2.5:0.5b",
                api_key="ollama",
                api_base="http://localhost:11434",
            )
        ], []

    monkeypatch.setattr(planner_ai, "resolve_planner_ai_credential_candidates", fake_resolve_candidates)
    monkeypatch.setenv("PLANNER_AI_MAX_CONCURRENT", "1")
    monkeypatch.setenv("PLANNER_AI_QUEUE_WAIT_SEC", "0.1")

    _reset_planner_ai_limiter_state()
    sem = asyncio.Semaphore(1)
    asyncio.run(sem.acquire())
    planner_ai._PLANNER_AI_SEMAPHORE = sem
    planner_ai._PLANNER_AI_SEMAPHORE_SIZE = 1

    request = PlannerAiRequest(prompt="monitor telegram account_id bot_a01 setiap 5 menit")
    try:
        plan = asyncio.run(planner_ai.build_plan_with_ai_dari_dashboard(request))
    finally:
        sem.release()
        _reset_planner_ai_limiter_state()

    assert plan.planner_source == "rule_based"
    assert any("sedang sibuk" in item for item in plan.warnings)


def test_build_plan_with_ai_timeout_keeps_slot_busy_until_worker_done(monkeypatch):
    async def fake_resolve_candidates(_request):
        return [
            planner_ai.PlannerAiCredentials(
                provider="ollama",
                account_id="default",
                model_id="ollama/qwen2.5:0.5b",
                api_key="ollama",
                api_base="http://localhost:11434",
            )
        ], []

    def fake_jalankan(*_args, **_kwargs):
        time.sleep(0.35)
        return None, ["mock slow response"]

    monkeypatch.setattr(planner_ai, "resolve_planner_ai_credential_candidates", fake_resolve_candidates)
    monkeypatch.setattr(planner_ai, "_jalankan_smolagents", fake_jalankan)
    monkeypatch.setenv("PLANNER_AI_TIMEOUT_SEC", "0.1")
    monkeypatch.setenv("PLANNER_AI_MAX_CONCURRENT", "1")
    monkeypatch.setenv("PLANNER_AI_QUEUE_WAIT_SEC", "0.05")
    monkeypatch.setattr(planner_ai, "_planner_ai_timeout_sec", lambda: 0.1)
    monkeypatch.setattr(planner_ai, "_planner_ai_release_grace_sec", lambda: 0.4)

    _reset_planner_ai_limiter_state()
    request = PlannerAiRequest(prompt="monitor telegram account_id bot_a01 setiap 5 menit")

    async def run_scenario():
        first = asyncio.create_task(planner_ai.build_plan_with_ai_dari_dashboard(request))
        await asyncio.sleep(0.15)

        start = time.perf_counter()
        second = await planner_ai.build_plan_with_ai_dari_dashboard(request)
        second_latency = time.perf_counter() - start

        first_result = await first
        # Planner timeout sengaja membiarkan worker thread selesai di background.
        # Tunggu sebentar agar asyncio.run() tidak macet saat shutdown executor.
        await asyncio.sleep(0.3)
        return first_result, second, second_latency

    try:
        first_result, second_result, second_latency = asyncio.run(run_scenario())
    finally:
        _reset_planner_ai_limiter_state()

    assert first_result.planner_source == "rule_based"
    assert any("timeout" in item.lower() for item in first_result.warnings)

    assert second_result.planner_source == "rule_based"
    assert any("sedang sibuk" in item for item in second_result.warnings)
    assert second_latency < 0.25


def test_build_plan_with_ai_dashboard_success_hides_attempt_warning(monkeypatch):
    async def fake_resolve_candidates(_request):
        return [
            planner_ai.PlannerAiCredentials(
                provider="ollama",
                account_id="default",
                model_id="ollama/gemini-q8:latest",
                api_key="ollama",
                api_base="http://localhost:11434",
            )
        ], []

    def fake_jalankan(*_args, **_kwargs):
        return {
            "summary": "ok",
            "jobs": [
                {
                    "type": "monitor.channel",
                    "reason": "Pantau channel",
                    "schedule": None,
                    "inputs": {},
                }
            ],
        }, []

    monkeypatch.setattr(planner_ai, "resolve_planner_ai_credential_candidates", fake_resolve_candidates)
    monkeypatch.setattr(planner_ai, "_jalankan_smolagents", fake_jalankan)
    monkeypatch.setenv("PLANNER_AI_MAX_CONCURRENT", "1")
    monkeypatch.setenv("PLANNER_AI_QUEUE_WAIT_SEC", "0.5")
    monkeypatch.setenv("PLANNER_AI_TIMEOUT_SEC", "2")

    _reset_planner_ai_limiter_state()
    try:
        request = PlannerAiRequest(prompt="monitor telegram account_id bot_a01 tiap 30 detik")
        plan = asyncio.run(planner_ai.build_plan_with_ai_dari_dashboard(request))
    finally:
        _reset_planner_ai_limiter_state()

    assert plan.jobs
    assert not any("Mencoba planner AI lewat" in item for item in plan.warnings)
