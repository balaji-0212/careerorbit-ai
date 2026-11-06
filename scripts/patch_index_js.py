"""Patch JavaScript in careerorbit/web/static/index.html to implement
Telegram Ingestion Observability, rich Channel Table, and Telegram Desktop Export Modal handlers.
"""
from pathlib import Path

html_path = Path("careerorbit/web/static/index.html")
content = html_path.read_text(encoding="utf-8")

# Target block for loadTelegramStatus and renderChannelsTable
target_js_block = """                if (diagChannelsCount) diagChannelsCount.innerText = tgChannels.length;
                if (diagAccessibleChannels) diagAccessibleChannels.innerText = tgChannels.filter(c => c.status === 'ACTIVE').length;
                if (diagWaCount) diagWaCount.innerText = waSources.length;

                if (channelStatusEl) {
                    if (data.channel_ingestion_working) {
                        channelStatusEl.className = 'badge badge-green';
                        channelStatusEl.innerText = `${chSummary.active_accessible || tgChannels.length} Channels Active`;
                    } else if (tgChannels.length > 0) {
                        channelStatusEl.className = 'badge badge-amber';
                        channelStatusEl.innerText = 'Admin Rights Needed';
                    } else {
                        channelStatusEl.className = 'badge badge-secondary';
                        channelStatusEl.innerText = 'No Channels Registered';
                    }
                }

                if (diagChannelStateBadge) {
                    if (data.channel_ingestion_working) {
                        diagChannelStateBadge.className = 'badge badge-green';
                        diagChannelStateBadge.innerText = 'Active Reception';
                    } else if (tgChannels.length > 0) {
                        diagChannelStateBadge.className = 'badge badge-amber';
                        diagChannelStateBadge.innerText = 'Permissions Required';
                    } else {
                        diagChannelStateBadge.className = 'badge badge-secondary';
                        diagChannelStateBadge.innerText = 'Not Configured';
                    }
                }"""

replacement_js_block = """                const accessibleCount = tgChannels.filter(c => c.status === 'ACTIVE' && (c.can_receive_messages === 1 || c.can_receive_messages === true || c.can_receive_messages === undefined)).length;
                if (diagChannelsCount) diagChannelsCount.innerText = tgChannels.length;
                if (diagAccessibleChannels) diagAccessibleChannels.innerText = accessibleCount;
                if (diagWaCount) diagWaCount.innerText = waSources.length;

                const sourcesBadge = document.getElementById('inbox-sources-count-badge');
                if (sourcesBadge) sourcesBadge.innerText = `${tgChannels.length} Sources (${accessibleCount} Active)`;

                const syncMetricsEl = document.getElementById('diag-sync-metrics-text');
                const m = data.last_sync_metrics || {};
                if (syncMetricsEl) {
                    if (m.timestamp) {
                        syncMetricsEl.innerHTML = `<strong>${m.updates_fetched || 0}</strong> fetched &bull; <strong style="color:#34d399;">${m.messages_stored || 0}</strong> stored &bull; <strong style="color:#fbbf24;">${m.duplicates_skipped || 0}</strong> skipped &bull; <strong style="color:#f87171;">${m.rejected_count || 0}</strong> rejected`;
                    } else {
                        syncMetricsEl.innerText = 'Worker active; waiting for incoming updates';
                    }
                }

                if (channelStatusEl) {
                    if (accessibleCount > 0) {
                        channelStatusEl.className = 'badge badge-green';
                        channelStatusEl.innerText = `${accessibleCount} Channel${accessibleCount > 1 ? 's' : ''} Active`;
                    } else if (tgChannels.length > 0) {
                        channelStatusEl.className = 'badge badge-amber';
                        channelStatusEl.innerText = 'Action Required: 0 Accessible';
                    } else {
                        channelStatusEl.className = 'badge badge-secondary';
                        channelStatusEl.innerText = 'No Channels Registered';
                    }
                }

                if (diagChannelStateBadge) {
                    if (accessibleCount > 0) {
                        diagChannelStateBadge.className = 'badge badge-green';
                        diagChannelStateBadge.innerText = `Active (${accessibleCount} Ingesting)`;
                    } else if (tgChannels.length > 0) {
                        diagChannelStateBadge.className = 'badge badge-red';
                        diagChannelStateBadge.innerText = 'Permissions Blocked';
                    } else {
                        diagChannelStateBadge.className = 'badge badge-secondary';
                        diagChannelStateBadge.innerText = 'No Channels';
                    }
                }"""

assert target_js_block in content, "target_js_block not found in index.html"
content = content.replace(target_js_block, replacement_js_block, 1)

# Target renderChannelsTable implementation
target_table_fn = """        function renderChannelsTable(channels) {
            const container = document.getElementById('diag-channels-table-container');
            if (!container) return;

            if (!channels || !channels.length) {
                container.innerHTML = `
                    <div style="font-size: 12px; color: var(--text-muted); padding: 12px; text-align: center; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                        No Telegram channels or groups registered yet. Enter <code>@channel_username</code> above to test access.
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-subtle); text-align: left; color: var(--text-secondary);">
                                <th style="padding: 8px 10px;">Source Name / Chat ID</th>
                                <th style="padding: 8px 10px;">Type</th>
                                <th style="padding: 8px 10px;">Status</th>
                                <th style="padding: 8px 10px;">Diagnosis & Guidance</th>
                                <th style="padding: 8px 10px; text-align: right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${channels.map(c => `
                                <tr style="border-bottom: 1px solid var(--border-subtle);">
                                    <td style="padding: 8px 10px;">
                                        <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(c.source_name || c.chat_id)}</div>
                                        <div style="font-size: 11px; color: var(--text-muted); font-family: monospace;">${escapeHtml(c.chat_id)}</div>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        <span class="badge badge-secondary" style="font-size: 10px;">${escapeHtml(c.source_type)}</span>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        <span class="badge ${c.status === 'ACTIVE' ? 'badge-green' : 'badge-amber'}" style="font-size: 10px;">
                                            ${escapeHtml(c.status)}
                                        </span>
                                    </td>
                                    <td style="padding: 8px 10px; font-size: 11px; color: var(--text-secondary); max-width: 320px;">
                                        ${escapeHtml(c.last_error || 'Access verified.')}
                                    </td>
                                    <td style="padding: 8px 10px; text-align: right; white-space: nowrap;">
                                        <button class="btn btn-secondary btn-sm" onclick="recheckCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px;">
                                            ↻ Re-check
                                        </button>
                                        <button class="btn btn-danger btn-sm" onclick="deleteCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px; margin-left: 4px;">
                                            ✕ Remove
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }"""

replacement_table_fn = """        function renderChannelsTable(channels) {
            const container = document.getElementById('diag-channels-table-container');
            if (!container) return;

            if (!channels || !channels.length) {
                container.innerHTML = `
                    <div style="font-size: 12px; color: var(--text-muted); padding: 14px; text-align: center; background: var(--bg-sidebar); border-radius: var(--radius-sm); border: 1px dashed var(--border-subtle);">
                        📢 No Telegram channels registered yet. Enter <code>@channel_username</code> or numerical Chat ID above, or forward an announcement to <strong>@CareerOrbitJobAssistantBot</strong>.
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 11.5px; background: var(--bg-sidebar); border-radius: var(--radius-sm);">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-subtle); text-align: left; color: var(--text-secondary); font-size: 11px; text-transform: uppercase;">
                                <th style="padding: 8px 10px;">Source & Identifier</th>
                                <th style="padding: 8px 10px;">Type & Visibility</th>
                                <th style="padding: 8px 10px;">Bot Role</th>
                                <th style="padding: 8px 10px;">Can Ingest?</th>
                                <th style="padding: 8px 10px;">Last Message</th>
                                <th style="padding: 8px 10px;">Diagnosis & Required Action</th>
                                <th style="padding: 8px 10px; text-align: right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${channels.map(c => {
                                const isAccessible = c.can_receive_messages === 1 || c.can_receive_messages === true;
                                const isMember = c.is_member === 1 || c.is_member === true;
                                const isPub = c.is_public === 1 || c.is_public === true;
                                const role = c.bot_role || (c.status === 'ACTIVE' ? 'administrator' : 'member');
                                
                                let roleBadge = `<span class="badge badge-secondary" style="font-size: 9.5px;">${escapeHtml(role)}</span>`;
                                if (role === 'administrator') roleBadge = `<span class="badge badge-green" style="font-size: 9.5px;">Administrator</span>`;
                                else if (role === 'member') roleBadge = `<span class="badge badge-amber" style="font-size: 9.5px;">Member</span>`;
                                else if (role === 'export_parser') roleBadge = `<span class="badge badge-blue" style="font-size: 9.5px;">Export File</span>`;
                                else if (role === 'forwarded') roleBadge = `<span class="badge badge-blue" style="font-size: 9.5px;">Forwarded</span>`;

                                const msgTime = c.last_message_at ? new Date(c.last_message_at).toLocaleDateString('en-IN', {
                                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                }) : 'None yet';

                                return `
                                <tr style="border-bottom: 1px solid var(--border-subtle);">
                                    <td style="padding: 8px 10px;">
                                        <div style="font-weight: 600; color: var(--text-main); font-size: 12px;">${escapeHtml(c.source_name || c.chat_id)}</div>
                                        <div style="font-size: 10.5px; color: var(--text-muted); font-family: monospace;">
                                            ${escapeHtml(c.chat_id)}${c.chat_username ? ` &bull; @${escapeHtml(c.chat_username)}` : ''}
                                        </div>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                            <span class="badge badge-secondary" style="font-size: 9.5px;">${escapeHtml(c.source_type.replace('telegram_', ''))}</span>
                                            <span class="badge ${isPub ? 'badge-blue' : 'badge-secondary'}" style="font-size: 9.5px;">${isPub ? 'Public' : 'Private'}</span>
                                        </div>
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        ${roleBadge}
                                    </td>
                                    <td style="padding: 8px 10px;">
                                        ${isAccessible ?
                                            `<span class="badge badge-green" style="font-size: 10px; font-weight: 600;">✅ YES (Receiving)</span>` :
                                            `<span class="badge badge-red" style="font-size: 10px; font-weight: 600;">❌ NO (Blocked)</span>`
                                        }
                                    </td>
                                    <td style="padding: 8px 10px; font-size: 11px;">
                                        <div style="color: var(--text-main);">${escapeHtml(msgTime)}</div>
                                        <div style="color: var(--text-muted); font-size: 10.5px;">${c.messages_count || 0} messages ingested</div>
                                    </td>
                                    <td style="padding: 8px 10px; font-size: 11px; max-width: 280px; color: var(--text-secondary); line-height: 1.4;">
                                        ${c.diagnosis ? `<div>${escapeHtml(c.diagnosis)}</div>` : ''}
                                        ${c.setup_instructions ? `<div style="margin-top: 3px; color: #fbbf24; font-size: 10.5px;">👉 <strong>Action:</strong> ${escapeHtml(c.setup_instructions)}</div>` : ''}
                                    </td>
                                    <td style="padding: 8px 10px; text-align: right; white-space: nowrap;">
                                        <button class="btn btn-secondary btn-sm" onclick="recheckCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px;">
                                            ↻ Re-check
                                        </button>
                                        <button class="btn btn-danger btn-sm" onclick="deleteCommunitySourceAction(${c.id})" style="font-size: 10px; padding: 3px 6px; margin-left: 4px;">
                                            ✕ Remove
                                        </button>
                                    </td>
                                </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }"""

assert target_table_fn in content, "target_table_fn not found in index.html"
content = content.replace(target_table_fn, replacement_table_fn, 1)

# Target triggerTelegramManualPoll toast
target_poll_toast = """                if (data.status === 'NOT_CONFIGURED') {
                    showToast('Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN in .env', 'warning');
                } else if (data.status === 'SUCCESS') {
                    const proc = data.processed_count || 0;
                    const skipped = data.skipped_count || 0;
                    const rec = data.received_count || proc;
                    if (rec > 0) {
                        showToast(`Telegram sync complete: ${proc} processed, ${skipped} duplicate/skipped.`, 'success');
                    } else {
                        showToast('Telegram sync complete: No new updates pending.', 'info');
                    }
                }"""

replacement_poll_toast = """                if (data.status === 'NOT_CONFIGURED') {
                    showToast('Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN in .env', 'warning');
                } else if (data.status === 'SUCCESS') {
                    const m = data.metrics || {};
                    const rec = data.received_count || m.updates_fetched || 0;
                    const stored = data.processed_count || m.messages_stored || 0;
                    const skipped = data.duplicates_skipped || m.duplicates_skipped || 0;
                    const cmds = data.commands_handled || m.commands_handled || 0;
                    const rej = data.rejected_count || m.rejected_count || 0;
                    const accCount = (commData && commData.sources ? commData.sources.filter(s => s.status === 'ACTIVE' && (s.can_receive_messages === 1 || s.can_receive_messages === true)).length : 0);

                    if (rec > 0) {
                        showToast(`Telegram sync complete: ${stored} messages stored, ${cmds} commands handled, ${skipped} duplicates skipped.`, 'success');
                    } else if (accCount === 0) {
                        showToast('Telegram sync: 0 updates fetched. Notice: 0 accessible channels are registered. Add @CareerOrbitJobAssistantBot as Administrator to channels or forward announcements.', 'info');
                    } else {
                        showToast(`Telegram sync complete: Checked ${accCount} accessible channels; no new posts pending.`, 'info');
                    }
                }"""

assert target_poll_toast in content, "target_poll_toast not found in index.html"
content = content.replace(target_poll_toast, replacement_poll_toast, 1)

# Add Telegram Export Modal functions to the end of the script
telegram_export_js = """
        // Telegram Desktop Export Modal Functions
        let telegramExportFileContent = null;
        let telegramExportFileName = '';
        let telegramPreviewItems = [];

        function openTelegramExportModal() {
            document.getElementById('tg-export-title').value = '';
            document.getElementById('tg-export-file').value = '';
            document.getElementById('tg-export-results').style.display = 'none';
            document.getElementById('tg-export-file-info').style.display = 'none';
            telegramExportFileContent = null;
            telegramExportFileName = '';
            telegramPreviewItems = [];
            document.getElementById('telegram-export-modal').classList.add('active');
        }

        function handleTelegramExportFileSelect(e) {
            const file = e.target.files[0];
            if (!file) return;
            telegramExportFileName = file.name;
            const infoEl = document.getElementById('tg-export-file-info');
            infoEl.style.display = 'block';
            infoEl.innerHTML = `Selected File: <strong>${escapeHtml(file.name)}</strong> (${(file.size / 1024).toFixed(1)} KB)`;

            const reader = new FileReader();
            reader.onload = function(evt) {
                telegramExportFileContent = evt.target.result;
            };
            if (file.name.endsWith('.html') || file.name.endsWith('.htm')) {
                reader.readAsText(file);
            } else {
                reader.readAsText(file);
            }
        }

        async function previewTelegramExport() {
            if (!telegramExportFileContent) {
                showToast('Please select a result.json or messages.html export file.', 'warning');
                return;
            }
            const btn = document.getElementById('btn-tg-export-preview');
            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerText = 'Parsing Export...';
            }

            try {
                const overrideTitle = document.getElementById('tg-export-title').value.trim();
                const res = await apiFetch('/api/telegram/export/parse-preview', {
                    method: 'POST',
                    body: JSON.stringify({
                        content: telegramExportFileContent,
                        filename: telegramExportFileName,
                        override_title: overrideTitle
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Parse failed');

                telegramPreviewItems = data.items || [];
                document.getElementById('tg-export-results').style.display = 'block';
                document.getElementById('tg-export-stats').innerHTML = `
                    <div style="font-weight: 600; color: var(--text-main); margin-bottom: 4px;">Channel: <strong>${escapeHtml(data.chat_name)}</strong> (Export: ${escapeHtml(data.filename)})</div>
                    <div style="display: flex; gap: 16px; flex-wrap: wrap; color: var(--text-secondary); font-size: 12px;">
                        <div>Total Messages: <strong>${data.total_raw_messages || 0}</strong></div>
                        <div>Career Relevant: <strong style="color: #34d399;">${data.career_relevant || 0}</strong></div>
                        <div>Job Leads: <strong style="color: #60a5fa;">${data.job_leads_count || 0}</strong></div>
                        <div>Personal/Service Skipped: <strong style="color: var(--text-muted);">${data.personal_skipped || 0}</strong></div>
                    </div>
                `;

                const listEl = document.getElementById('tg-export-items-list');
                if (!telegramPreviewItems.length) {
                    listEl.innerHTML = '<div style="font-size: 12px; color: var(--text-secondary); padding: 12px;">No career or learning opportunities detected in this export.</div>';
                    return;
                }

                listEl.innerHTML = telegramPreviewItems.map((item, idx) => `
                    <div style="background: rgba(15, 23, 42, 0.5); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                                <input type="checkbox" id="tg-exp-chk-${idx}" checked style="accent-color: var(--primary);">
                                <span class="badge ${item.is_job_lead ? 'badge-blue' : 'badge-green'}" style="font-size: 10px;">${escapeHtml(item.classification)}</span>
                                <strong style="color: var(--text-main);">${escapeHtml(item.sender_name || item.chat_name)}</strong>
                            </label>
                            <span style="color: var(--text-muted); font-size: 11px;">#${item.message_id} &bull; ${escapeHtml(item.timestamp_raw)}</span>
                        </div>
                        <div style="color: var(--text-secondary); white-space: pre-wrap; font-size: 11.5px; max-height: 60px; overflow-y: auto;">${escapeHtml(item.raw_text.slice(0, 180))}</div>
                    </div>
                `).join('');
            } catch (err) {
                showToast(`Failed to parse export: ${err.message}`, 'error');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        }

        async function confirmTelegramExportImport() {
            if (!telegramPreviewItems.length) {
                showToast('No items available to import.', 'warning');
                return;
            }
            const selectedItems = [];
            telegramPreviewItems.forEach((item, idx) => {
                const chk = document.getElementById(`tg-exp-chk-${idx}`);
                if (chk && chk.checked) {
                    selectedItems.push(item);
                }
            });

            if (!selectedItems.length) {
                showToast('Please select at least one item to import.', 'warning');
                return;
            }

            const btn = document.getElementById('btn-tg-confirm-import');
            if (btn) {
                btn.disabled = true;
                btn.innerText = 'Importing...';
            }

            try {
                const chatName = document.getElementById('tg-export-title').value.trim() || (telegramPreviewItems[0] ? telegramPreviewItems[0].chat_name : 'Telegram Channel');
                const chatId = telegramPreviewItems[0] ? telegramPreviewItems[0].chat_id : 'export';
                const res = await apiFetch('/api/telegram/export/import', {
                    method: 'POST',
                    body: JSON.stringify({
                        items: selectedItems,
                        chat_name: chatName,
                        chat_id: chatId,
                        filename: telegramExportFileName
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Import failed');

                showToast(`Telegram export imported: ${data.imported_count} messages ingested (${data.jobs_created} job leads, ${data.duplicates_count} duplicates skipped).`, 'success');
                closeModal('telegram-export-modal');
                await Promise.all([
                    loadInbox(),
                    loadTelegramStatus(),
                    fetchStats()
                ]);
            } catch (err) {
                showToast(`Import failed: ${err.message}`, 'error');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = 'Commit & Ingest Items';
                }
            }
        }
"""

# Insert right before the last closing script tag
content = content.replace("    </script>\r\n</body>", telegram_export_js + "    </script>\r\n</body>", 1)
if "    </script>\r\n</body>" not in content and "    </script>\n</body>" in content:
    content = content.replace("    </script>\n</body>", telegram_export_js + "    </script>\n</body>", 1)

html_path.write_text(content, encoding="utf-8", newline="\r\n")
print("JavaScript section patched successfully in index.html!")
