// Twitch Plays Pokemon - Frontend Application

class TPPApp {
    constructor() {
        this.ws = null;
        this.username = localStorage.getItem("tpp_username") || "Trainer" + Math.floor(100 + Math.random() * 900);
        this.scanlinesEnabled = true;

        this.adminPassword = sessionStorage.getItem("tpp_admin_password") || "";

        this.initDOM();
        this.initKeyboard();
        this.initControls();
        this.initAdminConsole();
        this.connectWebSocket();
    }

    initDOM() {
        this.dom = {
            appTitle: document.getElementById("app-title"),
            fps: document.getElementById("stat-fps"),
            viewers: document.getElementById("stat-viewers"),
            totalInputs: document.getElementById("stat-total-inputs"),
            queueBadge: document.getElementById("queue-size-badge"),
            
            modeTag: document.getElementById("current-mode-tag"),
            anarchyPct: document.getElementById("anarchy-pct"),
            democracyPct: document.getElementById("democracy-pct"),
            anarchyBar: document.getElementById("anarchy-bar"),
            democracyBar: document.getElementById("democracy-bar"),
            
            demRoundBox: document.getElementById("democracy-round-box"),
            demCountdown: document.getElementById("dem-countdown"),
            demVotesList: document.getElementById("dem-votes-list"),

            historyTicker: document.getElementById("input-history-ticker"),
            chatMessages: document.getElementById("chat-messages"),
            chatForm: document.getElementById("chat-form"),
            userInput: document.getElementById("username-input"),
            msgInput: document.getElementById("message-input"),

            saveBtn: document.getElementById("manual-save-btn"),

            // Admin elements
            adminOpenBtn: document.getElementById("admin-open-btn"),
            adminModal: document.getElementById("admin-modal"),
            adminCloseBtn: document.getElementById("admin-close-btn"),
            adminLoginView: document.getElementById("admin-login-view"),
            adminDashboardView: document.getElementById("admin-dashboard-view"),
            adminLoginForm: document.getElementById("admin-login-form"),
            adminPassInput: document.getElementById("admin-pass-input"),
            adminLoginMsg: document.getElementById("admin-login-msg"),
            adminSaveAllBtn: document.getElementById("admin-save-all-btn"),
            adminSaveStatus: document.getElementById("admin-save-status"),
            adminLogoutBtn: document.getElementById("admin-logout-btn"),
            adminClearQueueBtn: document.getElementById("admin-clear-queue-btn"),
            adminQueueLiveCount: document.getElementById("admin-queue-live-count"),
            adminSaveStateBtn: document.getElementById("admin-save-state-btn"),
            adminLoadStateBtn: document.getElementById("admin-load-state-btn"),
            adminSaveFeedback: document.getElementById("admin-save-feedback"),
            adminAnnouncementForm: document.getElementById("admin-announcement-form"),
            adminAnnouncementInput: document.getElementById("admin-announcement-input"),
            adminRomActualName: document.getElementById("admin-rom-actual-name")
        };

        this.dom.userInput.value = this.username;
        this.dom.userInput.addEventListener("change", (e) => {
            this.username = e.target.value.trim() || "Trainer";
            localStorage.setItem("tpp_username", this.username);
        });
    }

    connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log("[WS] Connected to Twitch Plays Pokemon server");
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleServerMessage(data);
            } catch (err) {
                console.error("[WS] Parse error:", err);
            }
        };

        this.ws.onclose = () => {
            console.warn("[WS] Disconnected. Reconnecting in 2 seconds...");
            setTimeout(() => this.connectWebSocket(), 2000);
        };
    }

    sendCommand(cmd) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: "command",
                user: this.username,
                text: cmd
            }));
        }
    }

    sendChat(text) {
        if (!text.trim()) return;
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: "chat",
                user: this.username,
                text: text.trim()
            }));
        }
    }

    initControls() {
        // Virtual Game Boy controller buttons
        document.querySelectorAll("[data-cmd]").forEach(btn => {
            const cmd = btn.getAttribute("data-cmd");
            const trigger = (e) => {
                e.preventDefault();
                this.sendCommand(cmd);
            };
            btn.addEventListener("click", trigger);
        });

        // Mode voting buttons
        document.querySelectorAll(".vote-mode-btn").forEach(btn => {
            const mode = btn.getAttribute("data-mode");
            btn.addEventListener("click", () => {
                this.sendCommand(mode);
            });
        });

        // Chat Form
        this.dom.chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const text = this.dom.msgInput.value;
            if (text) {
                this.sendChat(text);
                this.dom.msgInput.value = "";
            }
        });

        // Save State button
        this.dom.saveBtn.addEventListener("click", async () => {
            this.dom.saveBtn.disabled = true;
            this.dom.saveBtn.textContent = "Speichern...";
            try {
                const res = await fetch("/api/save", { method: "POST" });
                const json = await res.json();
                if (json.status === "saved") {
                    this.appendChatMessage("System", "💾 Speicherstand (Save State) erfolgreich gesichert!", "system");
                }
            } catch (e) {
                console.error("Save state error:", e);
            } finally {
                this.dom.saveBtn.disabled = false;
                this.dom.saveBtn.textContent = "💾 Save State";
            }
        });
    }

    initKeyboard() {
        const keyMap = {
            "ArrowUp": "up",
            "ArrowDown": "down",
            "ArrowLeft": "left",
            "ArrowRight": "right",
            "z": "a",
            "Z": "a",
            "x": "b",
            "X": "b",
            "Enter": "start",
            "Shift": "select"
        };

        window.addEventListener("keydown", (e) => {
            // Ignore if user is currently typing in input field
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
            if (activeTag === "input" || activeTag === "textarea") {
                return;
            }

            const cmd = keyMap[e.key];
            if (cmd) {
                e.preventDefault();
                this.sendCommand(cmd);
                
                // Highlight corresponding virtual button
                const btn = document.querySelector(`[data-cmd="${cmd}"]`);
                if (btn) {
                    btn.classList.add("keyboard-pressed");
                    setTimeout(() => btn.classList.remove("keyboard-pressed"), 120);
                }
            }
        });
    }

    handleServerMessage(msg) {
        switch (msg.type) {
            case "init":
            case "status_update":
                this.updateStatus(msg.status);
                break;
            case "executed_input":
                this.onInputExecuted(msg);
                if (msg.status) this.updateStatus(msg.status);
                break;
            case "chat_message":
                this.appendChatMessage(msg.user, msg.text, "user", msg.time);
                break;
            case "system_announcement":
                this.appendChatMessage("System", msg.text, "system");
                break;
            case "democracy_vote":
                if (msg.status) this.updateStatus(msg.status);
                break;
        }
    }

    updateStatus(status) {
        if (status.stream_title && this.dom.appTitle && this.dom.appTitle.textContent !== status.stream_title) {
            this.dom.appTitle.textContent = status.stream_title;
        }
        if (status.page_title && document.title !== status.page_title) {
            document.title = status.page_title;
        }

        if (status.fps !== undefined && this.dom.fps) {
            const fpsStr = (Number(status.fps) || 0).toFixed(1);
            if (this.dom.fps.textContent !== fpsStr) {
                this.dom.fps.textContent = fpsStr;
            }
        }
        if (status.viewers !== undefined && this.dom.viewers) {
            const viewersStr = String(status.viewers);
            if (this.dom.viewers.textContent !== viewersStr) {
                this.dom.viewers.textContent = viewersStr;
            }
        }
        if (status.total_inputs !== undefined && this.dom.totalInputs) {
            const totalStr = String(status.total_inputs);
            if (this.dom.totalInputs.textContent !== totalStr) {
                this.dom.totalInputs.textContent = totalStr;
            }
        }
        if (status.queue_size !== undefined && this.dom.queueBadge) {
            const qStr = `Warteschlange: ${status.queue_size}`;
            if (this.dom.queueBadge.textContent !== qStr) {
                this.dom.queueBadge.textContent = qStr;
            }
        }

        // Mode badge & bars
        const isAnarchy = status.mode === "anarchy";
        const modeText = isAnarchy ? "ANARCHIE" : "DEMOKRATIE";
        if (this.dom.modeTag && this.dom.modeTag.textContent !== modeText) {
            this.dom.modeTag.textContent = modeText;
            this.dom.modeTag.className = `mode-badge ${isAnarchy ? "anarchy" : "democracy"}`;
        }

        const anPct = Math.round(status.anarchy_percent ?? 100);
        const demPct = Math.round(status.democracy_percent ?? 0);
        if (this.dom.anarchyPct && this.dom.anarchyPct.textContent !== String(anPct)) {
            this.dom.anarchyPct.textContent = anPct;
            this.dom.anarchyBar.style.width = `${anPct}%`;
        }
        if (this.dom.democracyPct && this.dom.democracyPct.textContent !== String(demPct)) {
            this.dom.democracyPct.textContent = demPct;
            this.dom.democracyBar.style.width = `${demPct}%`;
        }

        // Democracy details box
        if (!isAnarchy) {
            if (this.dom.demRoundBox.style.display !== "block") {
                this.dom.demRoundBox.style.display = "block";
            }
            const cdStr = `${(status.democracy_remaining_sec || 0).toFixed(1)}s`;
            if (this.dom.demCountdown.textContent !== cdStr) {
                this.dom.demCountdown.textContent = cdStr;
            }
            
            const tally = status.democracy_tally || [];
            const tallyHash = tally.map(t => `${t.command}:${t.votes}`).join(",");
            if (this.lastTallyHash !== tallyHash) {
                this.lastTallyHash = tallyHash;
                if (tally.length > 0) {
                    this.dom.demVotesList.innerHTML = tally.map(item => `
                        <div class="dem-vote-item">
                            <span>${item.command.toUpperCase()}</span>
                            <span>${item.percent}% (${item.votes})</span>
                        </div>
                    `).join("");
                } else {
                    this.dom.demVotesList.innerHTML = `<div class="empty-hint">Stimmen werden gesammelt...</div>`;
                }
            }
        } else {
            if (this.dom.demRoundBox.style.display !== "none") {
                this.dom.demRoundBox.style.display = "none";
            }
        }

        // Recent inputs - only re-render when actual changes happen
        const currentInputs = status.recent_inputs || [];
        const inputsHash = currentInputs.map(i => `${i.command}-${i.user}-${i.time}`).join("|");
        if (this.lastInputsHash !== inputsHash) {
            this.lastInputsHash = inputsHash;
            this.renderRecentInputs(currentInputs);
        }
    }

    onInputExecuted(event) {
        // Sound disabled
    }

    renderRecentInputs(inputs) {
        const html = inputs.slice(0, 12).map(item => `
            <div class="history-item">
                <span class="history-cmd">${item.command}</span>
                <span class="history-user" title="${item.user}">${item.user}</span>
                <span class="history-source">${item.source}</span>
            </div>
        `).join("");
        this.dom.historyTicker.innerHTML = html;
    }

    appendChatMessage(author, text, type = "user", timestamp = "") {
        const timeStr = timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const row = document.createElement("div");
        row.className = `chat-msg ${type}`;
        
        if (type === "system") {
            row.innerHTML = `<span class="time">[${timeStr}]</span> <span class="body">${text}</span>`;
        } else {
            row.innerHTML = `<span class="time">[${timeStr}]</span> <span class="author">${escapeHtml(author)}:</span> <span class="body">${escapeHtml(text)}</span>`;
        }
        
        this.dom.chatMessages.appendChild(row);
        this.dom.chatMessages.scrollTop = this.dom.chatMessages.scrollHeight;
    }

    /* ==========================================================================
       ADMIN CONSOLE LOGIC
       ========================================================================== */

    initAdminConsole() {
        if (!this.dom.adminOpenBtn || !this.dom.adminModal) return;

        // Open modal
        this.dom.adminOpenBtn.addEventListener("click", () => {
            this.openAdminModal();
        });

        // Close modal
        this.dom.adminCloseBtn.addEventListener("click", () => {
            this.closeAdminModal();
        });

        // Background overlay click
        this.dom.adminModal.addEventListener("click", (e) => {
            if (e.target === this.dom.adminModal) {
                this.closeAdminModal();
            }
        });

        // Escape key to close
        window.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && this.dom.adminModal.style.display !== "none") {
                this.closeAdminModal();
            }
        });

        // Tab switching
        document.querySelectorAll(".admin-tab-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const targetTab = btn.getAttribute("data-tab");
                document.querySelectorAll(".admin-tab-btn").forEach(b => b.classList.remove("active"));
                document.querySelectorAll(".admin-tab-content").forEach(c => c.classList.remove("active"));
                btn.classList.add("active");
                const tabEl = document.getElementById(targetTab);
                if (tabEl) tabEl.classList.add("active");
            });
        });

        // Range inputs live labels
        const demSec = document.getElementById("admin-dem-seconds");
        const demSecVal = document.getElementById("admin-dem-seconds-val");
        if (demSec && demSecVal) {
            demSec.addEventListener("input", () => demSecVal.textContent = `${demSec.value}s`);
        }

        const demThresh = document.getElementById("admin-dem-threshold");
        const demThreshVal = document.getElementById("admin-dem-threshold-val");
        if (demThresh && demThreshVal) {
            demThresh.addEventListener("input", () => demThreshVal.textContent = `${demThresh.value}%`);
        }

        const userCd = document.getElementById("admin-user-cooldown");
        const userCdVal = document.getElementById("admin-user-cooldown-val");
        if (userCd && userCdVal) {
            userCd.addEventListener("input", () => userCdVal.textContent = `${Number(userCd.value).toFixed(1)}s`);
        }

        const qDelay = document.getElementById("admin-queue-delay");
        const qDelayVal = document.getElementById("admin-queue-delay-val");
        if (qDelay && qDelayVal) {
            qDelay.addEventListener("input", () => qDelayVal.textContent = `${qDelay.value}ms`);
        }

        // Speed buttons
        document.querySelectorAll(".admin-toggle-btn[data-speed]").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".admin-toggle-btn[data-speed]").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
            });
        });

        // Login submit
        this.dom.adminLoginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const pass = this.dom.adminPassInput.value.trim();
            if (!pass) return;

            this.dom.adminLoginMsg.textContent = "Prüfe Passwort...";
            this.dom.adminLoginMsg.className = "admin-status-msg";
            try {
                const res = await fetch("/api/admin/verify", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ password: pass })
                });
                if (res.ok) {
                    const data = await res.json();
                    this.adminPassword = pass;
                    sessionStorage.setItem("tpp_admin_password", pass);
                    this.dom.adminLoginMsg.textContent = "";
                    this.showAdminDashboard(data.settings, data.actual_rom, data.queue_size, data.available_roms);
                } else {
                    this.dom.adminLoginMsg.textContent = "Falsches Admin-Passwort!";
                    this.dom.adminLoginMsg.className = "admin-status-msg error";
                }
            } catch (err) {
                this.dom.adminLoginMsg.textContent = "Verbindungsfehler: " + err.message;
                this.dom.adminLoginMsg.className = "admin-status-msg error";
            }
        });

        // Logout
        this.dom.adminLogoutBtn.addEventListener("click", () => {
            this.adminPassword = "";
            sessionStorage.removeItem("tpp_admin_password");
            this.dom.adminDashboardView.style.display = "none";
            this.dom.adminLoginView.style.display = "block";
            this.dom.adminPassInput.value = "";
            this.dom.adminLoginMsg.textContent = "";
        });

        // Save All Settings
        this.dom.adminSaveAllBtn.addEventListener("click", async () => {
            await this.saveAdminSettings();
        });

        // Clear Queue Action
        this.dom.adminClearQueueBtn.addEventListener("click", async () => {
            this.dom.adminClearQueueBtn.disabled = true;
            this.dom.adminClearQueueBtn.textContent = "Wird geleert...";
            try {
                const res = await this.adminFetch("/api/admin/action", {
                    action: "clear_queue"
                });
                if (res.ok) {
                    const data = await res.json();
                    if (this.dom.adminQueueLiveCount) {
                        this.dom.adminQueueLiveCount.textContent = "0 Befehle";
                    }
                    this.showAdminSaveToast(`Warteschlange geleert (${data.cleared} verworfen)`);
                }
            } catch (err) {
                console.error("Clear queue error:", err);
            } finally {
                this.dom.adminClearQueueBtn.disabled = false;
                this.dom.adminClearQueueBtn.textContent = "🗑️ Warteschlange sofort leeren";
            }
        });

        // Save state action
        this.dom.adminSaveStateBtn.addEventListener("click", async () => {
            this.dom.adminSaveStateBtn.disabled = true;
            this.dom.adminSaveFeedback.textContent = "Speichere...";
            this.dom.adminSaveFeedback.className = "admin-status-msg";
            try {
                const res = await this.adminFetch("/api/admin/action", { action: "save_state" });
                if (res.ok) {
                    this.dom.adminSaveFeedback.textContent = "Spielstand erfolgreich auf Disk gesichert!";
                    this.dom.adminSaveFeedback.className = "admin-status-msg success";
                }
            } catch (e) {
                this.dom.adminSaveFeedback.textContent = "Fehler beim Speichern";
                this.dom.adminSaveFeedback.className = "admin-status-msg error";
            } finally {
                this.dom.adminSaveStateBtn.disabled = false;
            }
        });

        // Load state action
        this.dom.adminLoadStateBtn.addEventListener("click", async () => {
            if (!confirm("Letzten Autosave wirklich laden? Der aktuelle Fortschritt wird zurückgesetzt.")) return;
            this.dom.adminLoadStateBtn.disabled = true;
            this.dom.adminSaveFeedback.textContent = "Lade Spielstand...";
            this.dom.adminSaveFeedback.className = "admin-status-msg";
            try {
                const res = await this.adminFetch("/api/admin/action", { action: "load_state" });
                if (res.ok) {
                    this.dom.adminSaveFeedback.textContent = "Autosave erfolgreich geladen!";
                    this.dom.adminSaveFeedback.className = "admin-status-msg success";
                }
            } catch (e) {
                this.dom.adminSaveFeedback.textContent = "Fehler beim Laden";
                this.dom.adminSaveFeedback.className = "admin-status-msg error";
            } finally {
                this.dom.adminLoadStateBtn.disabled = false;
            }
        });

        // Announcement Form
        this.dom.adminAnnouncementForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const text = this.dom.adminAnnouncementInput.value.trim();
            if (!text) return;
            try {
                await this.adminFetch("/api/admin/action", { action: "announcement", data: text });
                this.dom.adminAnnouncementInput.value = "";
                this.showAdminSaveToast("Durchsage gesendet!");
            } catch (err) {
                console.error("Announcement error:", err);
            }
        });

        // Switch ROM Button
        const switchRomBtn = document.getElementById("admin-switch-rom-btn");
        if (switchRomBtn) {
            switchRomBtn.addEventListener("click", async () => {
                const romSelect = document.getElementById("admin-rom-select");
                const statusEl = document.getElementById("admin-rom-switch-status");
                if (!romSelect || !romSelect.value) return;

                const targetRom = romSelect.value;
                if (!confirm(`Möchtest du das Spiel wirklich zu "${targetRom}" wechseln?\nDer aktuelle Spielstand wird automatisch gesichert.`)) {
                    return;
                }

                switchRomBtn.disabled = true;
                if (statusEl) {
                    statusEl.textContent = `Wechsle zu ${targetRom}...`;
                    statusEl.className = "admin-status-msg";
                }

                try {
                    const res = await this.adminFetch("/api/admin/action", { action: "switch_rom", data: targetRom });
                    const json = await res.json();
                    if (res.ok) {
                        if (statusEl) {
                            statusEl.textContent = `Erfolgreich gewechselt zu ${targetRom}!`;
                            statusEl.className = "admin-status-msg success";
                        }
                        if (this.dom.adminRomActualName) {
                            this.dom.adminRomActualName.textContent = targetRom;
                        }
                        this.showAdminSaveToast(`Spiel gewechselt zu ${targetRom}`);
                    } else {
                        if (statusEl) {
                            statusEl.textContent = json.detail || "Fehler beim Wechseln der ROM";
                            statusEl.className = "admin-status-msg error";
                        }
                    }
                } catch (e) {
                    if (statusEl) {
                        statusEl.textContent = "Verbindungsfehler beim ROM-Wechsel";
                        statusEl.className = "admin-status-msg error";
                    }
                } finally {
                    switchRomBtn.disabled = false;
                }
            });
        }

        // ROM Drag & Drop Upload
        const dropzone = document.getElementById("admin-rom-dropzone");
        const fileInput = document.getElementById("admin-rom-file-input");

        if (dropzone && fileInput) {
            dropzone.addEventListener("click", () => fileInput.click());

            fileInput.addEventListener("change", () => {
                if (fileInput.files && fileInput.files.length > 0) {
                    this.uploadRomFile(fileInput.files[0]);
                    fileInput.value = "";
                }
            });

            ["dragenter", "dragover"].forEach(eventName => {
                dropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropzone.classList.add("dragover");
                });
            });

            ["dragleave", "dragend"].forEach(eventName => {
                dropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropzone.classList.remove("dragover");
                });
            });

            dropzone.addEventListener("drop", (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove("dragover");
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    this.uploadRomFile(e.dataTransfer.files[0]);
                }
            });
        }

        // Global Drag & Drop on open Admin Window
        window.addEventListener("dragover", (e) => {
            if (this.dom.adminModal && this.dom.adminModal.style.display === "flex" && this.adminPassword) {
                e.preventDefault();
            }
        });

        window.addEventListener("drop", (e) => {
            if (this.dom.adminModal && this.dom.adminModal.style.display === "flex" && this.adminPassword) {
                e.preventDefault();
                if (e.target && !e.target.closest("#admin-rom-dropzone")) {
                    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                        const tabBtn = document.querySelector('.admin-tab-btn[data-tab="tab-display"]');
                        if (tabBtn) tabBtn.click();
                        this.uploadRomFile(e.dataTransfer.files[0]);
                    }
                }
            }
        });
    }

    openAdminModal() {
        this.dom.adminModal.style.display = "flex";
        if (this.adminPassword) {
            this.loadAdminDashboard();
        } else {
            this.dom.adminLoginView.style.display = "block";
            this.dom.adminDashboardView.style.display = "none";
            setTimeout(() => this.dom.adminPassInput.focus(), 50);
        }
    }

    closeAdminModal() {
        this.dom.adminModal.style.display = "none";
    }

    async adminFetch(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Admin-Password": this.adminPassword
            },
            body: JSON.stringify(body)
        });
    }

    async loadAdminDashboard() {
        try {
            const res = await fetch("/api/admin/settings", {
                headers: { "X-Admin-Password": this.adminPassword }
            });
            if (res.ok) {
                const data = await res.json();
                this.showAdminDashboard(data.settings, data.actual_rom, data.queue_size, data.available_roms);
            } else {
                this.adminPassword = "";
                sessionStorage.removeItem("tpp_admin_password");
                this.dom.adminLoginView.style.display = "block";
                this.dom.adminDashboardView.style.display = "none";
            }
        } catch (e) {
            console.error("Load admin error:", e);
        }
    }

    showAdminDashboard(settings, actualRom, queueSize, availableRoms) {
        this.dom.adminLoginView.style.display = "none";
        this.dom.adminDashboardView.style.display = "block";

        if (actualRom && this.dom.adminRomActualName) {
            this.dom.adminRomActualName.textContent = actualRom;
        }
        if (queueSize !== undefined && this.dom.adminQueueLiveCount) {
            this.dom.adminQueueLiveCount.textContent = `${queueSize} Befehle`;
        }

        // Populate available ROMs dropdown
        this.populateRomDropdown(availableRoms, actualRom);

        if (!settings) return;

        // Forced mode radio
        const modeVal = settings.forced_mode || "auto";
        const radio = document.querySelector(`input[name="admin_forced_mode"][value="${modeVal}"]`);
        if (radio) radio.checked = true;

        // Democracy seconds
        const demSec = document.getElementById("admin-dem-seconds");
        const demSecVal = document.getElementById("admin-dem-seconds-val");
        if (demSec && demSecVal) {
            demSec.value = settings.democracy_round_seconds || 10;
            demSecVal.textContent = `${demSec.value}s`;
        }

        // Democracy threshold
        const demThresh = document.getElementById("admin-dem-threshold");
        const demThreshVal = document.getElementById("admin-dem-threshold-val");
        if (demThresh && demThreshVal) {
            demThresh.value = Math.round((settings.democracy_threshold || 0.6) * 100);
            demThreshVal.textContent = `${demThresh.value}%`;
        }

        // User cooldown
        const userCd = document.getElementById("admin-user-cooldown");
        const userCdVal = document.getElementById("admin-user-cooldown-val");
        if (userCd && userCdVal) {
            userCd.value = settings.user_vote_cooldown || 0;
            userCdVal.textContent = `${Number(userCd.value).toFixed(1)}s`;
        }

        // Queue paused
        const qPaused = document.getElementById("admin-queue-paused");
        if (qPaused) qPaused.checked = Boolean(settings.queue_paused);

        // Queue delay
        const qDelay = document.getElementById("admin-queue-delay");
        const qDelayVal = document.getElementById("admin-queue-delay-val");
        if (qDelay && qDelayVal) {
            qDelay.value = Math.round((settings.queue_input_delay || 0.15) * 1000);
            qDelayVal.textContent = `${qDelay.value}ms`;
        }

        // Show ROM
        const showRom = document.getElementById("admin-show-rom");
        if (showRom) showRom.checked = Boolean(settings.show_rom_name);

        // Speed buttons
        const spd = settings.emulation_speed || 1;
        document.querySelectorAll(".admin-toggle-btn[data-speed]").forEach(btn => {
            if (Number(btn.getAttribute("data-speed")) === spd) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
    }

    async saveAdminSettings() {
        this.dom.adminSaveAllBtn.disabled = true;
        this.dom.adminSaveAllBtn.textContent = "Speichere...";

        const forcedRadio = document.querySelector('input[name="admin_forced_mode"]:checked');
        const forcedMode = forcedRadio ? forcedRadio.value : "auto";

        const demSec = document.getElementById("admin-dem-seconds");
        const demThresh = document.getElementById("admin-dem-threshold");
        const userCd = document.getElementById("admin-user-cooldown");
        const qPaused = document.getElementById("admin-queue-paused");
        const qDelay = document.getElementById("admin-queue-delay");
        const showRom = document.getElementById("admin-show-rom");
        const speedBtn = document.querySelector(".admin-toggle-btn[data-speed].active");

        const payload = {
            forced_mode: forcedMode === "auto" ? null : forcedMode,
            democracy_round_seconds: demSec ? parseInt(demSec.value, 10) : 10,
            democracy_threshold: demThresh ? parseFloat(demThresh.value) / 100 : 0.6,
            user_vote_cooldown: userCd ? parseFloat(userCd.value) : 0.0,
            queue_paused: qPaused ? qPaused.checked : false,
            queue_input_delay: qDelay ? parseFloat(qDelay.value) / 1000 : 0.15,
            show_rom_name: showRom ? showRom.checked : false,
            emulation_speed: speedBtn ? parseInt(speedBtn.getAttribute("data-speed"), 10) : 1
        };

        try {
            const res = await fetch("/api/admin/settings", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-Admin-Password": this.adminPassword
                },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                this.showAdminSaveToast("✓ Gespeichert & Aktiv!");
            } else {
                this.showAdminSaveToast("Fehler beim Speichern");
            }
        } catch (e) {
            this.showAdminSaveToast("Verbindungsfehler");
        } finally {
            this.dom.adminSaveAllBtn.disabled = false;
            this.dom.adminSaveAllBtn.textContent = "💾 Einstellungen anwenden & speichern";
        }
    }

    showAdminSaveToast(msg) {
        if (!this.dom.adminSaveStatus) return;
        this.dom.adminSaveStatus.textContent = msg;
        setTimeout(() => {
            if (this.dom.adminSaveStatus.textContent === msg) {
                this.dom.adminSaveStatus.textContent = "";
            }
        }, 3000);
    }

    populateRomDropdown(availableRoms, selectedRom) {
        const romSelect = document.getElementById("admin-rom-select");
        if (!romSelect || !availableRoms) return;
        romSelect.innerHTML = "";
        if (availableRoms.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "Keine ROMs im Ordner roms/ gefunden";
            romSelect.appendChild(opt);
        } else {
            availableRoms.forEach(rom => {
                const opt = document.createElement("option");
                opt.value = rom;
                opt.textContent = rom;
                if (selectedRom && rom === selectedRom) {
                    opt.selected = true;
                }
                romSelect.appendChild(opt);
            });
        }
    }

    async uploadRomFile(file) {
        if (!file) return;

        const uploadBox = document.getElementById("admin-upload-status-box");
        const progressBar = document.getElementById("admin-upload-progress-bar");
        const uploadMsg = document.getElementById("admin-upload-msg");
        const romSelect = document.getElementById("admin-rom-select");

        const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
        if (ext !== ".gb" && ext !== ".gbc") {
            if (uploadBox && uploadMsg) {
                uploadBox.style.display = "block";
                uploadMsg.textContent = `Ungültige Datei "${file.name}". Bitte nur .gb oder .gbc Dateien hochladen!`;
                uploadMsg.className = "admin-status-msg error";
            }
            return;
        }

        if (file.size > 16 * 1024 * 1024) {
            if (uploadBox && uploadMsg) {
                uploadBox.style.display = "block";
                uploadMsg.textContent = `Datei zu groß (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximal 16 MB erlaubt.`;
                uploadMsg.className = "admin-status-msg error";
            }
            return;
        }

        if (uploadBox && uploadMsg && progressBar) {
            uploadBox.style.display = "block";
            progressBar.style.width = "25%";
            uploadMsg.textContent = `Lade "${file.name}" hoch (${(file.size / 1024).toFixed(0)} KB)...`;
            uploadMsg.className = "admin-status-msg";
        }

        try {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", "/api/admin/upload_rom", true);
            xhr.setRequestHeader("X-Admin-Password", this.adminPassword);
            xhr.setRequestHeader("X-ROM-Filename", encodeURIComponent(file.name));
            xhr.setRequestHeader("Content-Type", "application/octet-stream");

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable && progressBar) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = `${Math.max(20, pct)}%`;
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const resp = JSON.parse(xhr.responseText);
                        if (progressBar) progressBar.style.width = "100%";
                        if (uploadMsg) {
                            uploadMsg.innerHTML = `✅ <b>"${resp.filename}"</b> erfolgreich hochgeladen! ` +
                                `<button type="button" class="admin-btn admin-btn-primary" style="margin-left: 8px; padding: 4px 10px; font-size: 11px;" id="admin-quick-switch-btn">🎮 Jetzt starten</button>`;
                            uploadMsg.className = "admin-status-msg success";

                            const quickBtn = document.getElementById("admin-quick-switch-btn");
                            if (quickBtn) {
                                quickBtn.onclick = () => {
                                    const switchBtn = document.getElementById("admin-switch-rom-btn");
                                    if (romSelect) romSelect.value = resp.filename;
                                    if (switchBtn) switchBtn.click();
                                };
                            }
                        }

                        if (resp.available_roms && romSelect) {
                            this.populateRomDropdown(resp.available_roms, resp.filename);
                        }

                        this.showAdminSaveToast(`ROM "${resp.filename}" hinzugefügt`);
                    } catch (err) {
                        if (uploadMsg) {
                            uploadMsg.textContent = "Fehler beim Verarbeiten der Server-Antwort";
                            uploadMsg.className = "admin-status-msg error";
                        }
                    }
                } else {
                    let errMsg = "Fehler beim Hochladen";
                    try {
                        const err = JSON.parse(xhr.responseText);
                        if (err.detail) errMsg = err.detail;
                    } catch (_) {}
                    if (uploadMsg) {
                        uploadMsg.textContent = `❌ ${errMsg}`;
                        uploadMsg.className = "admin-status-msg error";
                    }
                }
            };

            xhr.onerror = () => {
                if (uploadMsg) {
                    uploadMsg.textContent = "Netzwerkfehler beim Hochladen";
                    uploadMsg.className = "admin-status-msg error";
                }
            };

            xhr.send(file);
        } catch (e) {
            if (uploadMsg) {
                uploadMsg.textContent = `Upload-Fehler: ${e.message}`;
                uploadMsg.className = "admin-status-msg error";
            }
        }
    }
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

document.addEventListener("DOMContentLoaded", () => {
    window.tppApp = new TPPApp();
});
