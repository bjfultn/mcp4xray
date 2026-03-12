/* mcp4xray — Observatory-themed chat client */

// --- State ---
let currentConversationId = null;
let isStreaming = false;
let currentAbortController = null;
const modelNames = {}; // id -> display name
let _lastTableResult = null; // full tabular tool result for CSV download

// --- DOM refs ---
const messagesEl = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatList = document.getElementById('chat-list');
const serverSelect = document.getElementById('server-select');
const modelSelect = document.getElementById('model-select');
const newChatBtn = document.getElementById('new-chat-btn');
const userNameEl = document.getElementById('user-name');
const logoutBtn = document.getElementById('logout-btn');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.getElementById('sidebar');
const sidebarDragHandle = document.getElementById('sidebar-drag-handle');
const sidebarExpandBtn = document.getElementById('sidebar-expand-btn');
const sidebarOverlay = document.getElementById('sidebar-overlay');

// --- Auth helpers ---

function getToken() {
    return localStorage.getItem('token');
}

function getUsername() {
    return localStorage.getItem('username') || '';
}

function getRole() {
    return localStorage.getItem('role') || 'user';
}

function authHeaders() {
    return { Authorization: 'Bearer ' + getToken() };
}

function requireAuth() {
    if (!getToken()) {
        window.location.href = '/login.html';
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    window.location.href = '/login.html';
}

// --- Init ---
document.addEventListener('DOMContentLoaded', init);

async function init() {
    if (!requireAuth()) return;

    restoreSidebarState();
    userNameEl.textContent = getUsername();
    showAdminLink();
    setupEventListeners();
    await Promise.all([fetchConfig(), loadConversations()]);

    // Load conversation from URL hash if present
    const hashMatch = window.location.hash.match(/^#chat\/(\d+)$/);
    if (hashMatch) {
        loadConversation(Number(hashMatch[1]));
    }
}

window.addEventListener('hashchange', () => {
    const m = window.location.hash.match(/^#chat\/(\d+)$/);
    if (m) {
        const id = Number(m[1]);
        if (id !== currentConversationId) loadConversation(id);
    }
});

function setupEventListeners() {
    sendBtn.onclick = sendMessage;
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
    });
    newChatBtn.addEventListener('click', newChat);
    logoutBtn.addEventListener('click', logout);
    document.getElementById('server-info-btn').addEventListener('click', showServerInfo);
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('server-info-modal').addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) closeModal();
    });
    document.getElementById('settings-btn').addEventListener('click', openSettings);
    document.getElementById('settings-modal-close').addEventListener('click', closeSettings);
    document.getElementById('settings-modal').addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) closeSettings();
    });
    document.getElementById('save-keys-btn').addEventListener('click', saveApiKeys);
    for (const btn of document.querySelectorAll('.key-toggle')) {
        btn.addEventListener('click', () => toggleKeyVisibility(btn.dataset.target));
    }
    for (const btn of document.querySelectorAll('.key-clear')) {
        btn.addEventListener('click', () => clearApiKey(btn.dataset.provider));
    }
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('mcp4xray-sidebar-collapsed', sidebar.classList.contains('collapsed'));
    });
    sidebarExpandBtn.addEventListener('click', () => {
        sidebar.classList.remove('collapsed');
        localStorage.setItem('mcp4xray-sidebar-collapsed', 'false');
    });
    sidebarOverlay.addEventListener('click', () => {
        sidebar.classList.add('collapsed');
        localStorage.setItem('mcp4xray-sidebar-collapsed', 'true');
    });
    setupSidebarResize();
    updateExpandBtnIcon();
    window.addEventListener('resize', updateExpandBtnIcon);
    userInput.addEventListener('focus', () => {
        if (window.innerWidth <= 768) {
            setTimeout(() => {
                userInput.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }, 300);
        }
    });
}

// --- Config ---

async function fetchConfig() {
    try {
        const res = await fetch('/api/config', { headers: authHeaders() });
        if (res.status === 401) { logout(); return; }
        const data = await res.json();

        serverSelect.innerHTML = '';
        for (const s of (data.servers || [])) {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = s.name;
            serverSelect.appendChild(opt);
        }

        modelSelect.innerHTML = '';
        const providerLabels = {
            anthropic: 'Anthropic',
            openai: 'OpenAI',
            gemini: 'Google',
            ollama: 'Ollama (local)',
        };
        const grouped = {};
        for (const m of (data.models || [])) {
            modelNames[m.id] = m.name || m.id;
            const p = m.provider || 'other';
            if (!grouped[p]) grouped[p] = [];
            grouped[p].push(m);
        }
        for (const [provider, models] of Object.entries(grouped)) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = providerLabels[provider] || provider;
            for (const m of models) {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name || m.id;
                optgroup.appendChild(opt);
            }
            modelSelect.appendChild(optgroup);
        }
    } catch (err) {
        console.error('Failed to fetch config:', err);
    }
}

// --- Conversations ---

async function loadConversations() {
    try {
        const res = await fetch('/api/conversations', { headers: authHeaders() });
        if (res.status === 401) { logout(); return; }
        const data = await res.json();
        renderConversationList(data.conversations || []);
    } catch (err) {
        console.error('Failed to load conversations:', err);
    }
}

function renderConversationList(conversations) {
    chatList.innerHTML = '';

    if (conversations.length === 0) {
        chatList.innerHTML = '<div style="padding:16px;color:var(--text-muted);font-size:0.84rem;text-align:center">No conversations yet</div>';
        return;
    }

    for (const conv of conversations) {
        const item = document.createElement('div');
        item.className = 'chat-item' + (conv.id === currentConversationId ? ' active' : '');
        item.dataset.id = conv.id;

        const title = conv.title || conv.server_name + ' / ' + (modelNames[conv.model] || conv.model);
        const date = new Date(conv.updated_at * 1000);
        const dateStr = formatDate(date);

        item.innerHTML =
            '<span class="chat-item-title">' + escapeHtml(title) + '</span>' +
            '<span class="chat-item-date">' + escapeHtml(dateStr) + '</span>' +
            '<button class="chat-item-delete" title="Delete">&times;</button>';

        item.addEventListener('click', (e) => {
            if (e.target.closest('.chat-item-delete')) {
                e.stopPropagation();
                deleteConversation(conv.id);
                return;
            }
            loadConversation(conv.id);
        });

        chatList.appendChild(item);
    }
}

async function loadConversation(id) {
    currentConversationId = id;
    history.replaceState(null, '', '#chat/' + id);

    document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.toggle('active', Number(el.dataset.id) === id);
    });

    if (window.innerWidth <= 768) {
        sidebar.classList.add('collapsed');
    }

    try {
        const res = await fetch('/api/conversations/' + id + '/messages', {
            headers: authHeaders(),
        });
        if (res.status === 401) { logout(); return; }
        const data = await res.json();
        renderAllMessages(data.messages || []);
    } catch (err) {
        console.error('Failed to load conversation:', err);
    }
}

async function deleteConversation(id) {
    if (!confirm('Delete this conversation?')) return;
    try {
        await fetch('/api/conversations/' + id, {
            method: 'DELETE',
            headers: authHeaders(),
        });
        if (id === currentConversationId) {
            currentConversationId = null;
            clearMessages();
        }
        await loadConversations();
    } catch (err) {
        console.error('Failed to delete conversation:', err);
    }
}

function newChat() {
    currentConversationId = null;
    history.replaceState(null, '', window.location.pathname);
    clearMessages();
    document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.remove('active');
    });
    userInput.focus();
}

async function generateTitle(convId) {
    try {
        const res = await fetch('/api/conversations/' + convId + '/generate-title', {
            method: 'POST',
            headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.title) {
            // Update sidebar item
            const item = chatList.querySelector('[data-id="' + convId + '"]');
            if (item) {
                const titleEl = item.querySelector('.chat-item-title');
                if (titleEl) titleEl.textContent = data.title;
            }
        }
    } catch {}
}

// --- Message rendering ---

function clearMessages() {
    messagesEl.innerHTML = '';
    showEmptyState();
}

function showEmptyState() {
    if (!messagesEl.querySelector('.empty-state')) {
        const div = document.createElement('div');
        div.className = 'empty-state';
        div.id = 'empty-state';
        div.innerHTML =
            '<div class="empty-state-icon">&#9733;</div>' +
            '<h2>X-ray Astronomy Archive Assistant</h2>' +
            '<p>Select a mission server and model, then ask about observations, sources, or archives.</p>';
        messagesEl.appendChild(div);
    }
}

function hideEmptyState() {
    const es = document.getElementById('empty-state');
    if (es) es.remove();
}

function renderAllMessages(messages) {
    messagesEl.innerHTML = '';

    if (messages.length === 0) {
        showEmptyState();
        return;
    }

    for (const msg of messages) {
        switch (msg.role) {
            case 'user':
                appendUserMessage(msg.content);
                break;
            case 'assistant':
                appendAssistantMessage(msg.content);
                break;
            case 'tool_call':
                appendSavedToolCall(msg.content);
                break;
            case 'tool_result':
                appendSavedToolResult(msg.content);
                break;
        }
    }

    scrollToBottom();
}

function appendUserMessage(content) {
    hideEmptyState();
    const msg = document.createElement('div');
    msg.className = 'message message-user';
    msg.innerHTML =
        '<div class="message-role">You</div>' +
        '<div class="message-content">' + escapeHtml(content) + '</div>';
    messagesEl.appendChild(msg);
    scrollToBottom();
}

function appendAssistantMessage(content) {
    hideEmptyState();
    const msg = document.createElement('div');
    msg.className = 'message message-assistant';
    msg.innerHTML =
        '<div class="message-role">Assistant</div>' +
        '<div class="message-content">' + renderMarkdown(content) + '</div>';
    messagesEl.appendChild(msg);
    hydratePendingTables(msg);
    scrollToBottom();
}

function appendSavedToolCall(content) {
    hideEmptyState();
    let toolInfo;
    try { toolInfo = JSON.parse(content); } catch { toolInfo = { name: 'unknown', arguments: {} }; }

    const toolBlock = document.createElement('div');
    toolBlock.className = 'tool-block complete';
    toolBlock.style.maxWidth = '780px';
    toolBlock.style.margin = '6px auto';

    const argsJson = JSON.stringify(toolInfo.arguments || {}, null, 2);

    toolBlock.innerHTML =
        '<div class="tool-block-header">' +
            '<span class="tool-check">&#10003;</span>' +
            '<span class="tool-block-name">' + escapeHtml(toolInfo.name || 'unknown') + '</span>' +
            '<button class="tool-block-toggle">Show args</button>' +
        '</div>' +
        '<div class="tool-block-args"><code>' + escapeHtml(argsJson) + '</code></div>';

    setupToggle(toolBlock, '.tool-block-args', '.tool-block-toggle', 'Show args', 'Hide args');
    messagesEl.appendChild(toolBlock);
    scrollToBottom();
}

function appendSavedToolResult(content) {
    hideEmptyState();

    let parsed = null;
    try { parsed = JSON.parse(content); } catch {}

    // Detect tabular data in the stored result
    let tableData = null;
    if (parsed && !parsed.is_error && Array.isArray(parsed.content)
        && parsed.content.length > 0 && parsed.content[0].type === 'text') {
        try {
            const inner = JSON.parse(parsed.content[0].text);
            if (Array.isArray(inner.columns) && Array.isArray(inner.rows)) {
                tableData = inner;
            }
        } catch {}
    }

    const toolBlock = document.createElement('div');
    toolBlock.className = 'tool-block complete';
    toolBlock.style.maxWidth = '780px';
    toolBlock.style.margin = '6px auto';
    toolBlock.style.borderColor = 'rgba(78, 204, 163, 0.15)';

    if (tableData) {
        const rowCount = tableData.row_count || tableData.rows.length;
        const cols = tableData.columns;
        const rows = tableData.rows.map(r =>
            Array.isArray(r) ? r : cols.map(c => r[c])
        );
        _lastTableResult = { columns: cols, rows: rows };

        toolBlock.innerHTML =
            '<div class="tool-block-header">' +
                '<span class="tool-check" style="color:var(--success)">&#10003;</span>' +
                '<span class="tool-block-name" style="color:var(--text-muted)">' +
                    escapeHtml(rowCount + ' rows, ' + cols.length + ' columns') +
                '</span>' +
            '</div>';

        const tableEl = buildSortableTable(cols, rows);
        toolBlock.appendChild(tableEl);
    } else {
        let prettyContent;
        try { prettyContent = JSON.stringify(parsed, null, 2); } catch { prettyContent = content; }

        toolBlock.innerHTML =
            '<div class="tool-block-header">' +
                '<span class="tool-check" style="color:var(--success)">&#9776;</span>' +
                '<span class="tool-block-name" style="color:var(--text-muted)">Result</span>' +
                '<button class="tool-block-toggle">Show result</button>' +
            '</div>' +
            '<div class="tool-block-result"><code>' + escapeHtml(prettyContent) + '</code></div>';

        setupToggle(toolBlock, '.tool-block-result', '.tool-block-toggle', 'Show result', 'Hide result');
    }

    messagesEl.appendChild(toolBlock);
    scrollToBottom();
}

function setupToggle(block, bodySelector, toggleSelector, showText, hideText) {
    const toggleBtn = block.querySelector(toggleSelector);
    const body = block.querySelector(bodySelector);
    toggleBtn.addEventListener('click', () => {
        const isVisible = body.classList.toggle('visible');
        toggleBtn.textContent = isVisible ? hideText : showText;
    });
}

// --- Streaming message send ---

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isStreaming) return;

    const server = serverSelect.value;
    const model = modelSelect.value;
    if (!server || !model) {
        alert('Please select a mission server and model.');
        return;
    }

    const isNewConversation = !currentConversationId;
    appendUserMessage(text);
    userInput.value = '';
    userInput.style.height = 'auto';
    setStreaming(true);
    showLoadingIndicator();

    currentAbortController = new AbortController();

    const body = {
        message: text,
        server_name: server,
        model_id: model,
    };
    if (currentConversationId) {
        body.conversation_id = currentConversationId;
    }

    let turnEl = null;
    let textBlockEl = null;

    function ensureTurn() {
        if (!turnEl) {
            turnEl = document.createElement('div');
            turnEl.className = 'turn';
            const loadingEl = document.getElementById('loading-indicator');
            if (loadingEl) {
                messagesEl.insertBefore(turnEl, loadingEl);
            } else {
                messagesEl.appendChild(turnEl);
            }
        }
        return turnEl;
    }

    function ensureTextBlock() {
        if (!textBlockEl) {
            textBlockEl = document.createElement('div');
            textBlockEl.className = 'turn-text';
            textBlockEl._rawText = '';
            ensureTurn().appendChild(textBlockEl);
        }
        return textBlockEl;
    }

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...authHeaders(),
            },
            body: JSON.stringify(body),
            signal: currentAbortController.signal,
        });

        if (res.status === 401) { logout(); return; }

        if (!res.ok) {
            removeLoadingIndicator();
            const errData = await res.json().catch(() => ({ detail: 'Request failed' }));
            appendError(errData.detail || 'Request failed with status ' + res.status);
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const rawLine of lines) {
                const line = rawLine.trim();
                if (!line.startsWith('data: ')) continue;

                let event;
                try { event = JSON.parse(line.slice(6)); } catch { continue; }

                switch (event.type) {
                    case 'conversation_id': {
                        if (event.conversation_id) {
                            currentConversationId = event.conversation_id;
                            history.replaceState(null, '', '#chat/' + event.conversation_id);
                            if (isNewConversation) {
                                // Add to sidebar immediately with placeholder title
                                const placeholder = server + ' / ' + (modelNames[model] || model);
                                const item = document.createElement('div');
                                item.className = 'chat-item active';
                                item.dataset.id = event.conversation_id;
                                item.innerHTML =
                                    '<span class="chat-item-title">' + escapeHtml(placeholder) + '</span>' +
                                    '<span class="chat-item-date">now</span>' +
                                    '<button class="chat-item-delete" title="Delete">&times;</button>';
                                const convId = event.conversation_id;
                                item.addEventListener('click', (e) => {
                                    if (e.target.closest('.chat-item-delete')) {
                                        e.stopPropagation();
                                        deleteConversation(convId);
                                        return;
                                    }
                                    loadConversation(convId);
                                });
                                document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
                                chatList.prepend(item);
                            }
                        }
                        break;
                    }

                    case 'text': {
                        removeLoadingIndicator();
                        const block = ensureTextBlock();
                        block._rawText += event.content;
                        block.innerHTML = renderMarkdown(block._rawText);
                        hydratePendingTables(block);
                        scrollToBottom();
                        break;
                    }

                    case 'tool_call': {
                        removeLoadingIndicator();
                        textBlockEl = null;

                        const toolBlock = document.createElement('div');
                        toolBlock.className = 'tool-block';

                        const argsJson = JSON.stringify(event.tool_args || {}, null, 2);

                        toolBlock.innerHTML =
                            '<div class="tool-block-header">' +
                                '<span class="spinner"></span>' +
                                '<span class="tool-block-name">' + escapeHtml(event.tool_name || 'unknown') + '</span>' +
                                '<button class="tool-block-toggle">Show args</button>' +
                            '</div>' +
                            '<div class="tool-block-args"><code>' + escapeHtml(argsJson) + '</code></div>';

                        setupToggle(toolBlock, '.tool-block-args', '.tool-block-toggle', 'Show args', 'Hide args');
                        ensureTurn().appendChild(toolBlock);
                        scrollToBottom();
                        break;
                    }

                    case 'tool_result': {
                        // Mark previous tool block as complete
                        if (turnEl) {
                            const pendingTools = turnEl.querySelectorAll('.tool-block:not(.complete)');
                            const lastTool = pendingTools[pendingTools.length - 1];
                            if (lastTool) {
                                lastTool.classList.add('complete');
                                const spinner = lastTool.querySelector('.spinner');
                                if (spinner) {
                                    spinner.outerHTML = '<span class="tool-check">&#10003;</span>';
                                }
                            }
                        }

                        // Check if this is a tabular result (has columns + rows)
                        let parsed = null;
                        try { parsed = JSON.parse(event.content || ''); } catch {}
                        const isTabular = parsed && !parsed.is_error
                            && Array.isArray(parsed.content)
                            && parsed.content.length > 0
                            && parsed.content[0].type === 'text';

                        let tableData = null;
                        if (isTabular) {
                            try {
                                const inner = JSON.parse(parsed.content[0].text);
                                if (Array.isArray(inner.columns) && Array.isArray(inner.rows)) {
                                    tableData = inner;
                                }
                            } catch {}
                        }

                        const resultBlock = document.createElement('div');
                        resultBlock.className = 'tool-block complete';
                        resultBlock.style.borderColor = 'rgba(78, 204, 163, 0.15)';

                        if (tableData) {
                            // Render as sortable table and stash for markdown table download
                            const rowCount = tableData.row_count || tableData.rows.length;
                            const cols = tableData.columns;
                            const rows = tableData.rows.map(r =>
                                Array.isArray(r) ? r : cols.map(c => r[c])
                            );
                            _lastTableResult = { columns: cols, rows: rows };

                            resultBlock.innerHTML =
                                '<div class="tool-block-header">' +
                                    '<span class="tool-check" style="color:var(--success)">&#10003;</span>' +
                                    '<span class="tool-block-name" style="color:var(--text-muted)">' +
                                        escapeHtml(rowCount + ' rows, ' + cols.length + ' columns') +
                                    '</span>' +
                                '</div>';

                            const tableEl = buildSortableTable(cols, rows);
                            resultBlock.appendChild(tableEl);
                        } else {
                            let prettyContent;
                            try { prettyContent = JSON.stringify(parsed, null, 2); }
                            catch { prettyContent = event.content || ''; }

                            resultBlock.innerHTML =
                                '<div class="tool-block-header">' +
                                    '<span class="tool-check" style="color:var(--success)">&#9776;</span>' +
                                    '<span class="tool-block-name" style="color:var(--text-muted)">Result</span>' +
                                    '<button class="tool-block-toggle">Show result</button>' +
                                '</div>' +
                                '<div class="tool-block-result"><code>' + escapeHtml(prettyContent) + '</code></div>';

                            setupToggle(resultBlock, '.tool-block-result', '.tool-block-toggle', 'Show result', 'Hide result');
                        }

                        ensureTurn().appendChild(resultBlock);
                        textBlockEl = null;
                        showLoadingIndicator();
                        scrollToBottom();
                        break;
                    }

                    case 'error':
                        removeLoadingIndicator();
                        appendError(event.content || 'Unknown error');
                        break;

                    case 'done':
                        removeLoadingIndicator();
                        if (turnEl) {
                            for (const el of turnEl.querySelectorAll('.tool-block:not(.complete)')) {
                                el.remove();
                            }
                        }
                        turnEl = null;
                        textBlockEl = null;
                        break;
                }
            }
        }
    } catch (err) {
        removeLoadingIndicator();
        if (err.name === 'AbortError') {
            if (turnEl) {
                for (const el of turnEl.querySelectorAll('.tool-block:not(.complete)')) {
                    el.remove();
                }
                const note = document.createElement('div');
                note.className = 'stopped-note';
                note.textContent = 'Stopped';
                turnEl.appendChild(note);
            }
        } else {
            appendError('Connection error: ' + err.message);
        }
    } finally {
        currentAbortController = null;
        setStreaming(false);
        if (isNewConversation && currentConversationId) {
            // Fire title generation immediately (don't await — runs in background)
            generateTitle(currentConversationId);
        }
        await loadConversations();
    }
}

function stopStreaming() {
    if (currentAbortController) {
        currentAbortController.abort();
    }
}

function appendError(text) {
    hideEmptyState();
    const el = document.createElement('div');
    el.className = 'chat-error';
    el.textContent = text;
    messagesEl.appendChild(el);
    scrollToBottom();
}

function setStreaming(active) {
    isStreaming = active;
    if (active) {
        sendBtn.textContent = 'Stop';
        sendBtn.classList.add('stop');
        sendBtn.disabled = false;
        sendBtn.onclick = stopStreaming;
    } else {
        sendBtn.textContent = 'Send';
        sendBtn.classList.remove('stop');
        sendBtn.disabled = false;
        sendBtn.onclick = sendMessage;
    }
    userInput.disabled = active;
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Loading indicator (asterisk + astronomy words) ---

const ASTRO_WORDS = [
    // telescope & hardware
    'Polishing mirrors',
    'Aligning baffles',
    'Warming up CCDs',
    'Cooling down CCDs',
    'Rebooting telescope',
    'Tapping the gauge',
    'Jiggling the antenna',
    'Tuning the detector',
    'Nudging the aspect',
    'Petting the satellite',
    'Greasing optics',
    'Rotating solar panels',
    'Degassing the chamber',
    'Focusing the optics',
    'Checking the thermostat',
    'Realigning gratings',
    'Swapping filters',
    'Recocking the shutter',
    'Buffing the Wolter',
    'Tightening the baffles',
    'Replacing a fuse',
    'Updating firmware',
    'Cycling the power',
    'Turning it off and on',
    // sources & targets
    'Asking the Crab',
    'Poking Sgr A*',
    'Waking Chandra',
    'Whispering to XMM',
    'Bothering HEASARC',
    'Staring at Cas A',
    'Stalking Cyg X-1',
    'Pinging Vela X-1',
    'Disturbing Cen A',
    'Provoking a magnetar',
    'Annoying a pulsar',
    'Startling a quasar',
    'Cornering an AGN',
    'Interrogating M87',
    'Surveying Perseus',
    'Orbiting Sco X-1',
    'Approaching Her X-1',
    'Visiting the Bullet',
    // archive & data
    'Dusting off archive',
    'Shaking VOTable',
    'Bribing TAP server',
    'Feeding the pipeline',
    'Wrangling catalogs',
    'Pleading with ADQL',
    'Flattering the API',
    'Negotiating bandwidth',
    'Clearing the cache',
    'Refreshing the token',
    'Parsing the XML',
    'Unzipping the FITS',
    'Defragmenting archive',
    'Indexing columns',
    'Paginating results',
    'Sorting by flux',
    'Joining tables',
    'Flattening nested JSON',
    'Escaping wildcards',
    'Retrying the query',
    'Waiting in queue',
    'Downloading slowly',
    'Unpickling data',
    // software woes
    'Restarting CIAO',
    'Summoning HEASOFT',
    'Placating SAS',
    'Compiling from source',
    'Updating CALDB',
    'Sourcing the bashrc',
    'Setting PFILES',
    'Chasing a segfault',
    'Reading the traceback',
    'Googling the error',
    'Checking Stack Overflow',
    'Upgrading Python',
    'Downgrading Python',
    'Pinning dependencies',
    'Breaking the build',
    'Fixing the build',
    'Clearing IRAF cache',
    'Recompiling XSPEC',
    // photons & physics
    'Tickling photons',
    'Herding photons',
    'Contemplating photons',
    'Counting to ten keV',
    'Collecting soft photons',
    'Dodging cosmic rays',
    'Scolding cosmic rays',
    'Shushing background',
    'Absorbing column density',
    'Scattering off mirrors',
    'Diffracting politely',
    'Fluorescing iron',
    'Compton scattering',
    'Inverse Compton-ing',
    'Bremsstrahlung-ing',
    'Synchrotron-ing',
    'Photoionizing plasma',
    // pileup grief cycle
    'Suspecting pileup',
    'Denying pileup',
    'Accepting pileup',
    'Bargaining with pileup',
    'Modeling the pileup',
    'Ignoring the pileup',
    // calibration & analysis
    'Admiring the PSF',
    'Trusting the ARF',
    'Doubting the RMF',
    'Questioning the background',
    'Blaming the Sun',
    'Blaming the background',
    'Blaming the weather',
    'Blaming South Atlantic',
    'Losing a factor of 2',
    'Finding a factor of 2',
    'Losing a factor of pi',
    'Rounding aggressively',
    'Squeezing significance',
    'Fudging error bars',
    'Inflating error bars',
    'Hiding systematics',
    'Normalizing something',
    'Renormalizing again',
    'Thawing all parameters',
    'Freezing everything',
    'Unfreezing nH',
    'Refreezing nH',
    'Adding a powerlaw',
    'Adding another Gaussian',
    'Removing the Gaussian',
    'Trying a broken powerlaw',
    'Giving up on chi-squared',
    'Switching to C-stat',
    // display & plotting
    'Zooming in',
    'Zooming out',
    'Rotating image',
    'Unrotating image',
    'Toggling log scale',
    'Choosing colormap',
    'Regretting colormap',
    'Trying viridis',
    'Going back to ds9',
    'Adjusting the stretch',
    'Enhancing contrast',
    'Smoothing too much',
    'Unsmoothing',
    'Binning adaptively',
    'Rebinning again',
    'Overlaying contours',
    'Removing contours',
    'Labeling the axes',
    'Fixing the legend',
    'Exporting to PNG',
    'Exporting to PDF',
    'Rasterizing vectors',
    // human activities
    'Refreshing coffee',
    'Microwaving tea',
    'Checking email',
    'Ignoring Slack',
    'Pretending to know',
    'Faking confidence',
    'Looking busy',
    'Stalling for time',
    'Thinking deeply',
    'Pondering existence',
    'Reading the manual',
    'Ignoring warnings',
    'Checking notes',
    'Asking a postdoc',
    'Phoning Cambridge',
    'Emailing Vilspa',
    'Filing a bug report',
    'Closing the bug report',
    'Reopening the bug',
    'Writing it down',
    'Forgetting it',
    'Guessing units',
    'Converting epochs',
    'Squinting harder',
    'Adjusting monocle',
    'Consulting oracle',
    // classic silly
    'Reticulating splines',
    'Reversing polarity',
    'Engaging flux capacitor',
    'Recalibrating vibes',
    'Flipping bits',
    'Depixelating',
    'Enhancing the image',
    'Rotating the turbolift',
    'Charging the lasers',
    'Warming up warp drive',
];

let loadingWordInterval = null;

function showLoadingIndicator() {
    removeLoadingIndicator();
    const el = document.createElement('div');
    el.className = 'loading-indicator';
    el.id = 'loading-indicator';

    const word = ASTRO_WORDS[Math.floor(Math.random() * ASTRO_WORDS.length)];

    el.innerHTML = '<div class="loading-indicator-inner">' +
        '<span class="loading-asterisk">*</span>' +
        '<span class="loading-word">' + escapeHtml(word) + '</span>' +
    '</div>';

    messagesEl.appendChild(el);
    scrollToBottom();

    const wordEl = el.querySelector('.loading-word');
    loadingWordInterval = setInterval(() => {
        const newWord = ASTRO_WORDS[Math.floor(Math.random() * ASTRO_WORDS.length)];
        wordEl.style.opacity = '0';
        setTimeout(() => {
            wordEl.textContent = newWord;
            wordEl.style.opacity = '1';
        }, 200);
    }, 3000);
}

function removeLoadingIndicator() {
    if (loadingWordInterval) {
        clearInterval(loadingWordInterval);
        loadingWordInterval = null;
    }
    const el = document.getElementById('loading-indicator');
    if (el) el.remove();
}

// --- Sortable data table builder (ported from TAPchat) ---

function buildSortableTable(columns, rows, downloadData) {
    const sortedRows = rows.slice();
    let sortCol = -1;
    let sortAsc = true;

    const dlCols = downloadData ? downloadData.columns : columns;
    const dlRows = downloadData ? downloadData.rows : sortedRows;

    const container = document.createElement('div');
    container.className = 'table-container';

    // Header with download button
    const header = document.createElement('div');
    header.className = 'table-header';
    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'table-download-btn';
    downloadBtn.textContent = downloadData
        ? 'Download CSV (' + dlRows.length + ' rows)'
        : 'Download CSV';
    downloadBtn.addEventListener('click', () => downloadCSV(dlCols, dlRows));
    header.appendChild(downloadBtn);
    container.appendChild(header);

    // Scrollable table
    const scrollDiv = document.createElement('div');
    scrollDiv.className = 'table-scroll';

    const table = document.createElement('table');
    table.className = 'data-table';

    // thead with sortable columns
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    const thElements = [];
    for (let i = 0; i < columns.length; i++) {
        const th = document.createElement('th');
        th.className = 'sortable';
        th.textContent = columns[i];
        th.addEventListener('click', () => onSort(i));
        headRow.appendChild(th);
        thElements.push(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    scrollDiv.appendChild(table);
    container.appendChild(scrollDiv);

    function fillBody() {
        tbody.innerHTML = '';
        for (const row of sortedRows) {
            const tr = document.createElement('tr');
            for (const val of row) {
                const td = document.createElement('td');
                const s = val == null ? '' : String(val);
                // Detect links
                const m = s.match(/^https?:\/\/\S+$/);
                if (m) {
                    const a = document.createElement('a');
                    a.href = s;
                    a.textContent = s.length > 60 ? s.slice(0, 57) + '...' : s;
                    a.target = '_blank';
                    a.rel = 'noopener';
                    td.appendChild(a);
                } else {
                    td.textContent = s;
                }
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
    }

    function onSort(colIdx) {
        if (sortCol === colIdx) {
            sortAsc = !sortAsc;
        } else {
            sortCol = colIdx;
            sortAsc = true;
        }
        sortedRows.sort((a, b) => {
            const va = a[colIdx], vb = b[colIdx];
            if (va == null && vb == null) return 0;
            if (va == null) return 1;
            if (vb == null) return -1;
            // Try numeric comparison
            const na = Number(va), nb = Number(vb);
            if (!isNaN(na) && !isNaN(nb)) {
                return sortAsc ? na - nb : nb - na;
            }
            const sa = String(va), sb = String(vb);
            return sortAsc ? sa.localeCompare(sb) : sb.localeCompare(sa);
        });
        for (let i = 0; i < thElements.length; i++) {
            thElements[i].className = i === colIdx
                ? 'sortable ' + (sortAsc ? 'sort-asc' : 'sort-desc')
                : 'sortable';
        }
        fillBody();
    }

    fillBody();
    return container;
}

function downloadCSV(columns, rows) {
    const esc = (v) => {
        if (v == null) return '';
        const s = String(v);
        return s.includes(',') || s.includes('"') || s.includes('\n')
            ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const lines = [columns.map(esc).join(',')];
    for (const row of rows) { lines.push(row.map(esc).join(',')); }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mcp4xray_table.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Parse a markdown table block into {columns, rows} for buildSortableTable
function parseMarkdownTable(block) {
    const lines = block.trim().split('\n').filter(l => l.trim());
    if (lines.length < 2) return null;
    const stripMd = (s) => s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*(.+?)\*/g, '$1').replace(/`([^`]+)`/g, '$1');
    const parseRow = (line) => line.split('|').slice(1, -1).map(c => stripMd(c.trim()));
    const columns = parseRow(lines[0]);
    if (columns.length === 0) return null;
    const isSep = /^\|[\s\-:]+(\|[\s\-:]+)+\|?\s*$/.test(lines[1]);
    const dataStart = isSep ? 2 : 1;
    const rows = [];
    for (let i = dataStart; i < lines.length; i++) {
        rows.push(parseRow(lines[i]));
    }
    return { columns, rows };
}

// --- Markdown renderer ---

// Marker for deferred table rendering
let _tableCounter = 0;
const _pendingTables = {};

function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Extract markdown tables FIRST, before inline formatting mangles cell contents.
    // parseMarkdownTable strips markdown formatting from cells itself.
    html = html.replace(
        /((?:^\|.+\|[ \t]*$\n?){2,})/gm,
        (block) => {
            const raw = block.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
            const parsed = parseMarkdownTable(raw);
            if (!parsed) return block;
            const id = 'md-table-' + (++_tableCounter);
            _pendingTables[id] = parsed;
            return '<div id="' + id + '"></div>';
        }
    );

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return '<pre><code>' + code + '</code></pre>';
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bold / italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><\/p>/g, '');

    // Single newlines -> <br>
    html = html.replace(/(?<!<\/pre>)\n(?!<)/g, '<br>');

    return html;
}

// Replace pending table placeholders with sortable table DOM elements.
// Call this after setting innerHTML with renderMarkdown() output.
function hydratePendingTables(container) {
    for (const [id, parsed] of Object.entries(_pendingTables)) {
        const placeholder = container.querySelector('#' + id);
        if (placeholder) {
            const tableEl = buildSortableTable(parsed.columns, parsed.rows, _lastTableResult);
            placeholder.replaceWith(tableEl);
        }
        delete _pendingTables[id];
    }
}

// --- Sidebar resize ---

function restoreSidebarState() {
    const savedWidth = localStorage.getItem('mcp4xray-sidebar-width');
    if (savedWidth) {
        const w = parseInt(savedWidth);
        if (w >= 200 && w <= 500) {
            document.documentElement.style.setProperty('--sidebar-width', w + 'px');
        }
    }
    if (localStorage.getItem('mcp4xray-sidebar-collapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }
}

function setupSidebarResize() {
    let startX, startWidth;

    sidebarDragHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        sidebar.classList.add('resizing');
        sidebarDragHandle.classList.add('dragging');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });

    function onMouseMove(e) {
        const newWidth = Math.min(500, Math.max(200, startWidth + (e.clientX - startX)));
        document.documentElement.style.setProperty('--sidebar-width', newWidth + 'px');
    }

    function onMouseUp() {
        sidebar.classList.remove('resizing');
        sidebarDragHandle.classList.remove('dragging');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        localStorage.setItem('mcp4xray-sidebar-width', sidebar.offsetWidth);
    }

    sidebarDragHandle.addEventListener('touchstart', (e) => {
        startX = e.touches[0].clientX;
        startWidth = sidebar.offsetWidth;
        sidebar.classList.add('resizing');
        sidebarDragHandle.classList.add('dragging');
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);
    });

    function onTouchMove(e) {
        e.preventDefault();
        const newWidth = Math.min(500, Math.max(200, startWidth + (e.touches[0].clientX - startX)));
        document.documentElement.style.setProperty('--sidebar-width', newWidth + 'px');
    }

    function onTouchEnd() {
        sidebar.classList.remove('resizing');
        sidebarDragHandle.classList.remove('dragging');
        document.removeEventListener('touchmove', onTouchMove);
        document.removeEventListener('touchend', onTouchEnd);
        localStorage.setItem('mcp4xray-sidebar-width', sidebar.offsetWidth);
    }
}

function updateExpandBtnIcon() {
    if (window.innerWidth <= 768) {
        sidebarExpandBtn.innerHTML = '\u2630';
    } else {
        sidebarExpandBtn.innerHTML = '&raquo;';
    }
}

function showAdminLink() {
    if (getRole() === 'admin') {
        const header = document.querySelector('.sidebar-header h1');
        if (header && !document.querySelector('.admin-link')) {
            const link = document.createElement('a');
            link.href = '/admin.html';
            link.className = 'admin-link';
            link.textContent = 'Admin';
            header.parentElement.insertBefore(link, sidebarToggle);
        }
    }
}

// --- Settings Modal (API Keys) ---

async function openSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.remove('hidden');

    // Clear inputs
    for (const input of modal.querySelectorAll('input[data-provider]')) {
        input.value = '';
    }
    document.getElementById('key-ollama-url').value = '';

    // Load current masked keys
    try {
        const res = await fetch('/api/settings/api-keys', { headers: authHeaders() });
        if (res.status === 401) { logout(); return; }
        if (!res.ok) return;
        const data = await res.json();
        const keys = data.keys || {};

        for (const [provider, info] of Object.entries(keys)) {
            const status = document.getElementById('status-' + provider);
            if (status && info.masked_key) {
                status.textContent = 'Current: ' + info.masked_key;
                status.className = 'key-status has-key';
            }
            // Show saved ollama base_url
            if (provider === 'ollama' && info.base_url) {
                document.getElementById('key-ollama-url').value = info.base_url;
                if (status && !info.masked_key) {
                    status.textContent = 'Custom base URL set';
                    status.className = 'key-status has-key';
                }
            }
        }
        // Clear status for providers without keys
        for (const p of ['anthropic', 'openai', 'gemini', 'ollama']) {
            if (!keys[p]) {
                const status = document.getElementById('status-' + p);
                if (status) {
                    status.textContent = 'Using server default';
                    status.className = 'key-status';
                }
            }
        }
    } catch (err) {
        console.error('Failed to load API keys:', err);
    }
}

function closeSettings() {
    document.getElementById('settings-modal').classList.add('hidden');
}

async function saveApiKeys() {
    const btn = document.getElementById('save-keys-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const inputs = document.querySelectorAll('#settings-modal input[data-provider]');
    let saved = 0;

    for (const input of inputs) {
        const provider = input.dataset.provider;
        const value = input.value.trim();
        if (!value) continue;

        try {
            const res = await fetch('/api/settings/api-keys', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ provider, api_key: value }),
            });
            if (res.ok) {
                saved++;
                input.value = '';
                const status = document.getElementById('status-' + provider);
                if (status) {
                    status.textContent = 'Saved';
                    status.className = 'key-status saved';
                }
            }
        } catch (err) {
            console.error('Failed to save key for ' + provider + ':', err);
        }
    }

    // Save ollama base_url
    const ollamaUrl = document.getElementById('key-ollama-url').value.trim();
    if (ollamaUrl) {
        try {
            const res = await fetch('/api/settings/api-keys', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ provider: 'ollama', base_url: ollamaUrl }),
            });
            if (res.ok) {
                saved++;
                const status = document.getElementById('status-ollama');
                if (status) {
                    status.textContent = 'Saved';
                    status.className = 'key-status saved';
                }
            }
        } catch (err) {
            console.error('Failed to save ollama base URL:', err);
        }
    }

    btn.disabled = false;
    btn.textContent = saved > 0 ? 'Saved!' : 'Save Keys';
    if (saved > 0) {
        setTimeout(() => { btn.textContent = 'Save Keys'; }, 1500);
    }
}

async function clearApiKey(provider) {
    try {
        const res = await fetch('/api/settings/api-keys/' + provider, {
            method: 'DELETE',
            headers: authHeaders(),
        });
        if (res.ok) {
            const status = document.getElementById('status-' + provider);
            if (status) {
                status.textContent = 'Using server default';
                status.className = 'key-status';
            }
            const input = document.getElementById('key-' + provider);
            if (input) input.value = '';
        }
    } catch (err) {
        console.error('Failed to clear key:', err);
    }
}

function toggleKeyVisibility(targetId) {
    const input = document.getElementById(targetId);
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
}

// --- Server Info Modal ---

async function showServerInfo(e) {
    e.preventDefault();
    const serverName = serverSelect.value;
    if (!serverName) return;

    const modal = document.getElementById('server-info-modal');
    const modalName = document.getElementById('modal-server-name');
    const modalBody = document.getElementById('modal-body');

    modalName.textContent = serverName;
    modalBody.innerHTML = '<div class="modal-loading">Connecting...</div>';
    modal.classList.remove('hidden');

    try {
        const res = await fetch('/api/server-info?server_name=' + encodeURIComponent(serverName), {
            headers: authHeaders(),
        });
        if (res.status === 401) { logout(); return; }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            modalBody.innerHTML = '<div class="modal-error">' + escapeHtml(err.detail || 'Failed to connect') + '</div>';
            return;
        }
        const data = await res.json();
        renderServerInfo(modalBody, data);
    } catch (err) {
        modalBody.innerHTML = '<div class="modal-error">Connection error: ' + escapeHtml(err.message) + '</div>';
    }
}

function renderServerInfo(container, data) {
    let html = '';

    // URL
    html += '<div class="modal-section">' +
        '<div class="modal-section-title">Endpoint</div>' +
        '<div class="modal-url">' + escapeHtml(data.url) + '</div>' +
    '</div>';

    // Instructions
    if (data.instructions) {
        html += '<div class="modal-section">' +
            '<div class="modal-section-title">Instructions</div>' +
            '<div class="modal-instructions">' + escapeHtml(data.instructions) + '</div>' +
        '</div>';
    }

    // Tools
    const tools = data.tools || [];
    html += '<div class="modal-section">' +
        '<div class="modal-section-title">Tools (' + tools.length + ')</div>';

    if (tools.length === 0) {
        html += '<div style="color:var(--text-muted);font-style:italic">No tools available</div>';
    } else {
        for (const tool of tools) {
            html += '<div class="modal-tool">' +
                '<div class="modal-tool-name">' + escapeHtml(tool.name) + '</div>';
            if (tool.description) {
                html += '<div class="modal-tool-desc">' + escapeHtml(tool.description) + '</div>';
            }
            const schema = tool.inputSchema;
            if (schema && schema.properties) {
                const params = Object.keys(schema.properties);
                const required = schema.required || [];
                if (params.length > 0) {
                    html += '<div class="modal-tool-params">';
                    for (const p of params) {
                        const isReq = required.includes(p);
                        html += '<span>' + escapeHtml(p) + (isReq ? '' : '?') + '</span>';
                    }
                    html += '</div>';
                }
            }
            html += '</div>';
        }
    }

    html += '</div>';
    container.innerHTML = html;
}

function closeModal() {
    document.getElementById('server-info-modal').classList.add('hidden');
}

// --- Utilities ---

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(d) {
    if (!(d instanceof Date)) d = new Date(d);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
