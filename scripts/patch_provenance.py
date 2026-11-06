"""Patch provenanceBlock in renderInboxCard in careerorbit/web/static/index.html"""
from pathlib import Path

html_path = Path("careerorbit/web/static/index.html")
content = html_path.read_text(encoding="utf-8")

old_prov = """            // Truthful Provenance Block
            const provenanceBlock = channel === 'whatsapp' ? `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(5, 150, 105, 0.12); border: 1px solid rgba(5, 150, 105, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #34d399;">📄 WhatsApp Chat Export (.txt)</span>
                    <span>•</span>
                    <span>Group: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || 'Export')}</strong></span>
                    <span>•</span>
                    <span>Sender: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || 'Admin')}</strong></span>
                    ${extracted.timestamp_raw ? `<span>•</span><span>Export Timestamp: <strong style="color: var(--text-main);">${escapeHtml(extracted.timestamp_raw)}</strong></span>` : ''}
                    ${item.message_id ? `<span>•</span><span>Line: #${item.message_id}</span>` : ''}
                </div>
            ` : `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(2, 132, 199, 0.12); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #38bdf8;">🤖 Telegram Bot API (@CareerOrbitJobAssistantBot)</span>
                    <span>•</span>
                    <span>Chat: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || item.chat_id || 'Direct')}</strong></span>
                    <span>•</span>
                    <span>Sender: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || item.sender_username || 'User')}</strong></span>
                    ${item.message_id ? `<span>•</span><span>Msg ID: #${item.message_id}</span>` : ''}
                </div>
            `;"""

new_prov = """            // Truthful Provenance Block
            let provenanceBlock = '';
            if (channel === 'whatsapp') {
                provenanceBlock = `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(5, 150, 105, 0.12); border: 1px solid rgba(5, 150, 105, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #34d399;">📄 WhatsApp Chat Export (.txt)</span>
                    <span>•</span>
                    <span>Group: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || 'Export')}</strong></span>
                    <span>•</span>
                    <span>Sender: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || 'Admin')}</strong></span>
                    ${extracted.timestamp_raw ? `<span>•</span><span>Export Timestamp: <strong style="color: var(--text-main);">${escapeHtml(extracted.timestamp_raw)}</strong></span>` : ''}
                    ${item.message_id ? `<span>•</span><span>Line: #${item.message_id}</span>` : ''}
                </div>`;
            } else if (extracted.export_format && extracted.export_format.startsWith('telegram_desktop')) {
                provenanceBlock = `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #818cf8;">📄 Telegram Desktop Export (.json)</span>
                    <span>•</span>
                    <span>Channel: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || 'Channel')}</strong></span>
                    <span>•</span>
                    <span>Msg: <strong>#${item.message_id}</strong></span>
                    ${extracted.timestamp_raw ? `<span>•</span><span>Date: <strong>${escapeHtml(extracted.timestamp_raw)}</strong></span>` : ''}
                    ${extracted.export_filename ? `<span>•</span><span>File: <code style="font-size:10.5px;">${escapeHtml(extracted.export_filename)}</code></span>` : ''}
                </div>`;
            } else if (extracted.is_forwarded) {
                provenanceBlock = `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #38bdf8;">⏩ Forwarded Channel Announcement</span>
                    <span>•</span>
                    <span>Channel: <strong style="color: var(--text-main);">${escapeHtml(extracted.origin_channel_title || item.chat_title)}</strong>${extracted.origin_channel_username ? ` (@${escapeHtml(extracted.origin_channel_username)})` : ''}</span>
                    <span>•</span>
                    <span>Original Msg: <strong>#${extracted.origin_message_id || item.message_id}</strong></span>
                    ${extracted.origin_link ? `<a href="${escapeHtml(extracted.origin_link)}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; text-decoration: underline; margin-left: auto;">↗ View Telegram Post</a>` : ''}
                </div>`;
            } else {
                provenanceBlock = `
                <div style="margin-bottom: 10px; padding: 6px 12px; background: rgba(2, 132, 199, 0.12); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: var(--radius-sm); font-size: 11.5px; color: var(--text-secondary); display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                    <span style="font-weight: 700; color: #38bdf8;">🤖 Telegram Bot API (@CareerOrbitJobAssistantBot)</span>
                    <span>•</span>
                    <span>Source: <strong style="color: var(--text-main);">${escapeHtml(item.chat_title || item.chat_id || 'Direct')}</strong></span>
                    <span>•</span>
                    <span>From: <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || item.sender_username || 'User')}</strong></span>
                    ${item.message_id ? `<span>•</span><span>Msg ID: #${item.message_id}</span>` : ''}
                    ${extracted.origin_link ? `<a href="${escapeHtml(extracted.origin_link)}" target="_blank" rel="noopener noreferrer" style="color: #60a5fa; text-decoration: underline; margin-left: auto;">↗ View Telegram Post</a>` : ''}
                </div>`;
            }"""

assert old_prov in content, "old_prov not found in index.html"
content = content.replace(old_prov, new_prov, 1)

html_path.write_text(content, encoding="utf-8", newline="\r\n")
print("Provenance block updated successfully!")
