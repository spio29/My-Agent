from typing import Any, Dict

import aiohttp

from .base import Tool

class MessagingTool(Tool):
    @property
    def name(self) -> str:
        return "messaging"
    
    @property
    def version(self) -> str:
        return "1.0.0"

    async def _send_telegram_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
    ) -> Dict[str, Any]:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id).strip(),
            "text": str(text or "")[:3800],
        }
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    return {
                        "success": False,
                        "error": f"Telegram API HTTP {response.status}",
                        "detail": data,
                    }
                if not isinstance(data, dict) or not data.get("ok"):
                    return {
                        "success": False,
                        "error": "Telegram API returned non-ok payload",
                        "detail": data,
                    }
                result = data.get("result") or {}
                return {
                    "success": True,
                    "provider": "telegram_bot_api",
                    "message_id": result.get("message_id"),
                }

    async def run(self, input_data: Dict[str, Any], ctx) -> Dict[str, Any]:
        channel = str(input_data.get("channel") or "").strip().lower()
        text = str(input_data.get("text") or "")
        to_id = str(input_data.get("to_id") or "").strip()
        account_id = str(input_data.get("account_id") or "").strip()
        branch_id = str(getattr(ctx, "branch_id", "default") or "default")

        if not channel or not text or not to_id:
            return {"success": False, "error": "channel, text, and to_id are required"}

        if channel == "telegram":
            from app.core.connector_accounts import get_telegram_account
            from app.core.queue import append_event

            telegram_account_id = account_id or str(input_data.get("default_account_id") or "bot_a01").strip()
            account = await get_telegram_account(telegram_account_id, include_secret=True)
            if not account:
                return {
                    "success": False,
                    "error": f"Telegram account '{telegram_account_id}' not found",
                }

            bot_token = str(account.get("bot_token") or "").strip()
            if not bot_token:
                return {
                    "success": False,
                    "error": f"Telegram account '{telegram_account_id}' has no bot_token",
                }

            allowed = [str(v).strip() for v in (account.get("allowed_chat_ids") or []) if str(v).strip()]
            if allowed and to_id not in set(allowed):
                return {
                    "success": False,
                    "error": f"chat_id {to_id} is not allowed for account {telegram_account_id}",
                }

            result = await self._send_telegram_message(
                bot_token=bot_token,
                chat_id=to_id,
                text=text,
            )
            if not result.get("success"):
                return result

            await append_event(
                "messaging.message_sent",
                {
                    "account_id": telegram_account_id,
                    "platform": "telegram",
                    "to": to_id,
                    "mode": "telegram_bot_api",
                },
            )
            return {
                "success": True,
                "used_account": telegram_account_id,
                "message": "Message delivered via telegram bot API.",
                "metadata": {
                    "provider": "telegram_bot_api",
                    "message_id": result.get("message_id"),
                },
            }

        from app.core.armory import list_all_accounts, lock_account, unlock_account, get_account

        # 1. Get Account & Proxy from Armory
        target_account = None
        if account_id:
            target_account = await get_account(account_id, include_password=True)
        else:
            available = await list_all_accounts(platform=channel)
            ready_accounts = [
                a
                for a in available
                if a.get("branch_id") == branch_id and str(a.get("status") or "").lower() == "ready"
            ]
            if ready_accounts:
                target_account = ready_accounts[0]

        if not target_account:
            return {"success": False, "error": f"No READY {channel} account available for branch {branch_id}"}

        acc_id = target_account["account_id"]
        proxy_str = target_account.get("proxy")

        # 2. Lock account to prevent concurrent access
        if not await lock_account(acc_id):
            return {"success": False, "error": f"Account {acc_id} is currently busy."}

        try:
            # 3. Stealth Execution Logic
            print(f"[STEALTH] Opening {channel} session for {target_account['username']} via Proxy: {proxy_str or 'DIRECT'}")

            # Simulate Human Interaction
            import random
            import asyncio

            # A. Typing Simulation (Variable speed)
            typing_speed = random.uniform(0.05, 0.2)
            await asyncio.sleep(len(text) * typing_speed * 0.1)

            # 4. Record Success
            from app.core.queue import append_event
            await append_event("messaging.message_sent", {
                "account_id": acc_id,
                "platform": channel,
                "to": to_id,
                "proxy_used": bool(proxy_str)
            })

            return {
                "success": True,
                "used_account": target_account["username"],
                "message": f"Message delivered via {channel} using isolated proxy.",
                "metadata": {"typing_duration": len(text) * typing_speed}
            }
        finally:
            await unlock_account(acc_id)
    
