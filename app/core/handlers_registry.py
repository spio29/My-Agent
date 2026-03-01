from .registry import tool_registry, policy_manager
from app.jobs.handlers.monitor_channel import run as monitor_channel_handler
from app.jobs.handlers.daily_report import run as daily_report_handler
from app.jobs.handlers.backup_export import run as backup_export_handler
from app.jobs.handlers.agent_workflow import run as agent_workflow_handler
from app.jobs.handlers.boardroom_execute import run as boardroom_execute_handler
from app.jobs.handlers.sales_followup import run as sales_followup_handler
from app.jobs.handlers.simulation_heavy import run as simulation_heavy_handler

# Register job handlers
peta_handler_job = {
    "monitor.channel": monitor_channel_handler,
    "report.daily": daily_report_handler,
    "backup.export": backup_export_handler,
    "agent.workflow": agent_workflow_handler,
    "boardroom.execute": boardroom_execute_handler,
    "sales.followup": sales_followup_handler,
    "simulation.heavy": simulation_heavy_handler,
}

# Set policies for each job type
policy_manager.set_allowlist("monitor.channel", ["metrics", "messaging"])
policy_manager.set_allowlist("report.daily", ["metrics", "messaging"])
policy_manager.set_allowlist("backup.export", ["files", "kv"])
policy_manager.set_allowlist("agent.workflow", ["http", "kv", "messaging", "files", "metrics", "command"])
policy_manager.set_allowlist("sales.followup", ["messaging", "metrics"])
policy_manager.set_allowlist("simulation.heavy", ["metrics"])

def get_handler(job_type: str):
    """Get handler function for a job type"""
    return peta_handler_job.get(job_type)
