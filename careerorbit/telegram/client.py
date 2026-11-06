"""Official Telegram Bot API Client for CareerOrbit AI.
Encapsulates secure communication with https://api.telegram.org/bot<TOKEN>.
Adheres strictly to token redaction, connection reuse, and retry policies.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from careerorbit.config.settings import SETTINGS

logger = logging.getLogger("careerorbit.telegram.client")


class TelegramAPIError(Exception):
    """Raised when Telegram Bot API responds with ok=false."""
    def __init__(self, message: str, error_code: Optional[int] = None, description: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code
        self.description = description


class TelegramClient:
    """Resilient HTTP client for the official Telegram Bot API."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self, token: Optional[str] = None, session: Optional[requests.Session] = None):
        self._token = (token if token is not None else SETTINGS.TELEGRAM_BOT_TOKEN).strip()
        
        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    @property
    def is_configured(self) -> bool:
        """True if non-empty bot token is present."""
        return bool(self._token)

    @property
    def masked_token(self) -> str:
        """Return masked token for logging and diagnostic outputs."""
        if not self._token:
            return ""
        if len(self._token) <= 10:
            return "***"
        return f"{self._token[:4]}...{self._token[-4:]}"

    def __repr__(self) -> str:
        return f"<TelegramClient token={self.masked_token} configured={self.is_configured}>"

    def _redact_token(self, text: str) -> str:
        """Ensure token is stripped from URLs and error strings."""
        if self._token and self._token in text:
            return text.replace(self._token, "[REDACTED_TELEGRAM_TOKEN]")
        return text

    def _build_url(self, method: str) -> str:
        if not self._token:
            raise ValueError("Telegram Bot token is not configured. Set TELEGRAM_BOT_TOKEN in .env or environment.")
        return f"{self.BASE_URL}/bot{self._token}/{method.lstrip('/')}"

    def _request(self, method: str, http_method: str = "POST", json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Execute HTTP request against Telegram Bot API and return 'result' payload."""
        url = self._build_url(method)
        try:
            if http_method.upper() == "GET":
                resp = self._session.get(url, params=params, timeout=timeout)
            else:
                resp = self._session.post(url, json=json_data, params=params, timeout=timeout)
            
            data = resp.json()
        except requests.RequestException as exc:
            safe_msg = self._redact_token(str(exc))
            logger.error("Network error during Telegram API call /%s: %s", method, safe_msg)
            raise TelegramAPIError(f"Telegram network communication failed: {safe_msg}") from exc
        except ValueError as exc:
            raise TelegramAPIError(f"Invalid JSON received from Telegram API /{method}: {resp.status_code}") from exc

        if not data.get("ok"):
            err_code = data.get("error_code")
            desc = data.get("description", "Unknown error")
            logger.warning("Telegram API error /%s [HTTP %s]: %s", method, err_code, desc)
            raise TelegramAPIError(f"Telegram API error {err_code}: {desc}", error_code=err_code, description=desc)

        return data.get("result", {})

    def get_me(self) -> Dict[str, Any]:
        """Test authentication and fetch bot details (/getMe)."""
        return self._request("getMe", http_method="GET", timeout=10.0)

    def get_updates(
        self,
        offset: Optional[int] = None,
        limit: int = 100,
        timeout: int = 10,
        allowed_updates: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch incoming updates via long polling (/getUpdates)."""
        params: Dict[str, Any] = {
            "timeout": timeout,
            "limit": limit
        }
        if offset is not None:
            params["offset"] = offset
        if allowed_updates is None:
            allowed_updates = ["message", "edited_message", "channel_post", "edited_channel_post", "my_chat_member"]
        params["allowed_updates"] = allowed_updates

        res = self._request("getUpdates", http_method="POST", json_data=params, timeout=float(timeout + 5))
        return res if isinstance(res, list) else []

    def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False
    ) -> Dict[str, Any]:
        """Send a message to a chat or channel (/sendMessage)."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        return self._request("sendMessage", http_method="POST", json_data=payload, timeout=15.0)

    def set_webhook(
        self,
        url: str,
        secret_token: Optional[str] = None,
        allowed_updates: Optional[List[str]] = None
    ) -> bool:
        """Register a webhook endpoint (/setWebhook)."""
        payload: Dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        if allowed_updates is None:
            payload["allowed_updates"] = ["message", "edited_message", "channel_post", "edited_channel_post", "my_chat_member"]
        else:
            payload["allowed_updates"] = allowed_updates
        
        res = self._request("setWebhook", http_method="POST", json_data=payload, timeout=15.0)
        return bool(res)

    def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        """Delete active webhook so getUpdates polling can resume (/deleteWebhook)."""
        payload = {"drop_pending_updates": drop_pending_updates}
        res = self._request("deleteWebhook", http_method="POST", json_data=payload, timeout=15.0)
        return bool(res)

    def get_webhook_info(self) -> Dict[str, Any]:
        """Get current webhook status (/getWebhookInfo)."""
        return self._request("getWebhookInfo", http_method="GET", timeout=10.0)

    def get_chat(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Fetch chat information (/getChat). Accepts numeric ID or @username."""
        return self._request("getChat", http_method="POST", json_data={"chat_id": chat_id}, timeout=10.0)

    def get_chat_member(self, chat_id: Union[int, str], user_id: Union[int, str]) -> Dict[str, Any]:
        """Fetch status and permissions of a chat member (/getChatMember)."""
        return self._request("getChatMember", http_method="POST", json_data={"chat_id": chat_id, "user_id": user_id}, timeout=10.0)

    def get_chat_administrators(self, chat_id: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch list of administrators in a chat or channel (/getChatAdministrators)."""
        res = self._request("getChatAdministrators", http_method="POST", json_data={"chat_id": chat_id}, timeout=10.0)
        return res if isinstance(res, list) else []

    def check_chat_access(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Verify whether the bot has access to a specific channel/group, inspect permissions,
        and provide actionable diagnostics and setup instructions."""
        if not self.is_configured:
            return {
                "accessible": False,
                "status": "NOT_CONFIGURED",
                "can_receive_messages": False,
                "chat_id": str(chat_id),
                "diagnosis": "TELEGRAM_BOT_TOKEN is not configured.",
                "setup_instructions": "Add TELEGRAM_BOT_TOKEN to your .env file."
            }

        try:
            bot_info = self.get_me()
            bot_id = bot_info.get("id")
            bot_username = bot_info.get("username", "CareerOrbitJobAssistantBot")
        except Exception as auth_err:
            return {
                "accessible": False,
                "status": "AUTH_FAILED",
                "can_receive_messages": False,
                "chat_id": str(chat_id),
                "diagnosis": f"Bot authentication failed: {self._redact_token(str(auth_err))}",
                "setup_instructions": "Verify that your TELEGRAM_BOT_TOKEN from @BotFather is valid."
            }

        try:
            chat = self.get_chat(chat_id)
        except TelegramAPIError as api_err:
            desc = (api_err.description or str(api_err) or "").lower()
            if api_err.error_code == 400 and "chat not found" in desc:
                return {
                    "accessible": False,
                    "status": "NOT_FOUND",
                    "can_receive_messages": False,
                    "chat_id": str(chat_id),
                    "diagnosis": f"Chat '{chat_id}' was not found. For public channels, ensure handle starts with '@'. For private channels, use numerical ID (e.g. -100xxxxxxxxxx).",
                    "setup_instructions": f"Invite @{bot_username} to the channel as an Administrator, then re-check access."
                }
            if api_err.error_code in (400, 403) and ("bot was kicked" in desc or "not a member" in desc or "chat_write_forbidden" in desc):
                return {
                    "accessible": False,
                    "status": "NOT_A_MEMBER",
                    "can_receive_messages": False,
                    "chat_id": str(chat_id),
                    "diagnosis": f"The bot @{bot_username} is not a member of this chat or was removed.",
                    "setup_instructions": f"Add @{bot_username} to the channel/group as an Administrator."
                }
            return {
                "accessible": False,
                "status": "API_ERROR",
                "can_receive_messages": False,
                "chat_id": str(chat_id),
                "diagnosis": f"Telegram API error {api_err.error_code}: {api_err.description}",
                "setup_instructions": "Verify channel name and bot permissions."
            }
        except Exception as exc:
            return {
                "accessible": False,
                "status": "NETWORK_ERROR",
                "can_receive_messages": False,
                "chat_id": str(chat_id),
                "diagnosis": f"Network error checking chat: {self._redact_token(str(exc))}",
                "setup_instructions": "Check internet connectivity and try again."
            }

        chat_real_id = chat.get("id")
        chat_title = chat.get("title") or chat.get("username") or str(chat_real_id)
        chat_type = chat.get("type", "channel")
        chat_username = chat.get("username")

        # Check membership & permissions for the bot
        member_status = "unknown"
        member_obj = {}
        try:
            if bot_id:
                member_obj = self.get_chat_member(chat_real_id, bot_id)
                member_status = member_obj.get("status", "unknown")
        except Exception as mem_err:
            logger.debug("Could not get chat member for %s: %s", chat_id, mem_err)

        is_pub = bool(chat_username)
        if chat_type == "channel":
            if member_status in ("creator", "administrator"):
                can_post = member_obj.get("can_post_messages", True)
                return {
                    "accessible": True,
                    "status": "ADMIN_ACTIVE",
                    "can_receive_messages": True,
                    "is_public": is_pub,
                    "is_member": True,
                    "chat_id": str(chat_real_id),
                    "chat_title": chat_title,
                    "chat_type": "channel",
                    "chat_username": chat_username,
                    "role": member_status,
                    "bot_role": member_status,
                    "can_post_messages": can_post,
                    "diagnosis": "Bot is an Administrator in this channel. Channel announcements will be ingested into Unified Inbox.",
                    "setup_instructions": "Channel ingestion is active and verified."
                }
            else:
                return {
                    "accessible": False,
                    "status": "PERMISSION_REQUIRED",
                    "can_receive_messages": False,
                    "is_public": is_pub,
                    "is_member": member_status in ("member", "restricted"),
                    "chat_id": str(chat_real_id),
                    "chat_title": chat_title,
                    "chat_type": "channel",
                    "chat_username": chat_username,
                    "role": member_status,
                    "bot_role": member_status,
                    "missing_permissions": ["administrator", "post_messages"],
                    "diagnosis": "Bot is present as a subscriber, NOT an Administrator. In Telegram channels, the Bot API only delivers channel posts to bots that are promoted to Administrator.",
                    "setup_instructions": f"Open Channel Settings -> Administrators -> Add Administrator -> Search @{bot_username} -> Grant Administrator rights."
                }

        elif chat_type in ("group", "supergroup"):
            if member_status in ("creator", "administrator"):
                return {
                    "accessible": True,
                    "status": "ADMIN_ACTIVE",
                    "can_receive_messages": True,
                    "is_public": is_pub,
                    "is_member": True,
                    "chat_id": str(chat_real_id),
                    "chat_title": chat_title,
                    "chat_type": chat_type,
                    "chat_username": chat_username,
                    "role": member_status,
                    "bot_role": member_status,
                    "diagnosis": "Bot is an Administrator in this group. All group announcements will be ingested.",
                    "setup_instructions": "Group ingestion is active and verified."
                }
            elif member_status == "member":
                return {
                    "accessible": True,
                    "status": "PRIVACY_RESTRICTED",
                    "can_receive_messages": False,
                    "is_public": is_pub,
                    "is_member": True,
                    "chat_id": str(chat_real_id),
                    "chat_title": chat_title,
                    "chat_type": chat_type,
                    "chat_username": chat_username,
                    "role": "member",
                    "bot_role": "member",
                    "diagnosis": "Bot is a standard member in this group. Due to Telegram Group Privacy Mode, it will NOT receive regular messages; it only receives direct commands and explicit mentions (@CareerOrbitJobAssistantBot).",
                    "setup_instructions": f"To capture all community alerts: Either promote @{bot_username} to Administrator, or disable Privacy Mode in @BotFather (/setprivacy -> @{bot_username} -> Disable)."
                }
            else:
                return {
                    "accessible": False,
                    "status": "INACTIVE",
                    "can_receive_messages": False,
                    "is_public": is_pub,
                    "is_member": False,
                    "chat_id": str(chat_real_id),
                    "chat_title": chat_title,
                    "chat_type": chat_type,
                    "role": member_status,
                    "bot_role": member_status,
                    "diagnosis": f"Bot status in group is '{member_status}'.",
                    "setup_instructions": f"Add @{bot_username} to the group."
                }

        else:  # private
            return {
                "accessible": True,
                "status": "ACTIVE",
                "can_receive_messages": True,
                "is_public": False,
                "is_member": True,
                "chat_id": str(chat_real_id),
                "chat_title": chat_title,
                "chat_type": "private",
                "role": "user",
                "bot_role": "bot",
                "diagnosis": "Direct 1-on-1 private chat with bot.",
                "setup_instructions": "Direct messaging is fully active."
            }
