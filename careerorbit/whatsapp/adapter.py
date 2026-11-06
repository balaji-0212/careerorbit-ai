"""WhatsApp Ingestion Adapters for CareerOrbit AI.
Provides an extensible adapter architecture separating ingestion methods (chat export import,
future WhatsApp Business Cloud webhook, controlled forwarding) from the core intelligence pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pathlib import Path


class BaseWhatsAppAdapter(ABC):
    """Abstract base adapter for WhatsApp message sources."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Name of the adapter."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the adapter is configured and ready for use."""
        pass

    @abstractmethod
    def parse_preview(self, payload: Any, chat_title: str = "") -> Dict[str, Any]:
        """Parse source payload and generate a preview before committing."""
        pass

    @abstractmethod
    def commit_import(self, items: List[Dict[str, Any]], chat_title: str = "") -> Dict[str, Any]:
        """Commit selected items into Unified Inbox and Job tables."""
        pass


class WhatsAppExportAdapter(BaseWhatsAppAdapter):
    """Adapter for importing user-exported WhatsApp chat text files (.txt)."""

    @property
    def adapter_name(self) -> str:
        return "whatsapp_chat_export"

    @property
    def is_available(self) -> bool:
        return True

    def parse_preview(self, payload: Any, chat_title: str = "WhatsApp Export") -> Dict[str, Any]:
        from careerorbit.whatsapp.parser import WhatsAppChatExportParser
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", errors="replace")
        elif isinstance(payload, str):
            text = payload
        else:
            raise ValueError("Payload must be raw string or bytes")

        return WhatsAppChatExportParser.parse_text(text, chat_title=chat_title)

    def commit_import(self, items: List[Dict[str, Any]], chat_title: str = "WhatsApp Export") -> Dict[str, Any]:
        from careerorbit.whatsapp.parser import WhatsAppChatExportParser
        return WhatsAppChatExportParser.import_items(items, chat_title=chat_title)
