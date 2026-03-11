import os
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_workflow_default_redis_host_does_not_hang():
    script = textwrap.dedent(
        """
        import asyncio
        import pytest

        from app.jobs.handlers import agent_workflow


        class _FakeHttpTool:
            async def run(self, input_data, ctx):
                return {"success": True}


        class _Ctx:
            def __init__(self):
                self.tools = {"http": _FakeHttpTool()}
                self.job_id = "job_test"
                self.run_id = "run_test"


        async def main():
            result = await agent_workflow.run(_Ctx(), {})
            assert result["success"] is False
            assert "prompt" in result["error"]


        asyncio.run(main())
        print("after run")
        """
    )

    env = os.environ.copy()
    env.pop("REDIS_HOST", None)

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=8,
    )

    assert completed.returncode == 0, (
        f"subprocess failed:\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert "after run" in completed.stdout
