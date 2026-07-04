// --- APPLICATION STATE ---
let socket = null;
let chatHistory = []; // Array of {role: 'user'|'assistant', content: '...'}
let currentBotMessageElement = null;
let reconnectInterval = 3000; // Retry WebSocket connection every 3 seconds

// --- DOM ELEMENTS ---
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const btnClearChat = document.getElementById("btn-clear-chat");
const wsStatus = document.getElementById("ws-status");
const modelSelect = document.getElementById("model-select");
const customModelGroup = document.getElementById("custom-model-group");
const customModelInput = document.getElementById("custom-model-input");
const dragArea = document.getElementById("drag-area");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");
const uploadedFilesList = document.getElementById("uploaded-files-list");
const agentConsole = document.getElementById("agent-console");
const consoleLogs = document.getElementById("console-logs");

// --- WEBSOCKET CONNECTION ---
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
    
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    socket = new WebSocket(wsUrl);
    
    // Connection opened
    socket.onopen = () => {
        console.log("WebSocket connection established.");
        updateStatusUI(true);
    };
    
    // Connection closed
    socket.onclose = () => {
        console.log("WebSocket connection closed. Retrying...");
        updateStatusUI(false);
        setTimeout(connectWebSocket, reconnectInterval);
    };
    
    // Connection error
    socket.onerror = (error) => {
        console.error("WebSocket Error:", error);
        updateStatusUI(false);
    };
    
    // Receive message from server
    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
            case "status":
                // Agent logs thinking/tool usage
                showAgentLog(data.content);
                break;
                
            case "token":
                // Streamed answer tokens
                appendBotToken(data.content);
                break;
                
            case "done":
                // Generation finished
                finalizeBotMessage();
                break;
                
            case "error":
                // Server-side execution error
                appendErrorMessage(data.content);
                break;
        }
    };
}

function updateStatusUI(isConnected) {
    const dot = wsStatus.querySelector(".status-dot");
    const text = wsStatus.querySelector(".status-text");
    
    if (isConnected) {
        dot.className = "status-dot connected";
        text.textContent = "Connected";
    } else {
        dot.className = "status-dot disconnected";
        text.textContent = "Disconnected (reconnecting...)";
    }
}

// --- AGENT CONSOLE LOGS ---
function showAgentLog(message) {
    // Show console container
    agentConsole.classList.remove("hidden");
    
    const logLine = document.createElement("div");
    logLine.className = "console-line";
    
    if (message.startsWith("Thought:")) {
        logLine.classList.add("thought");
        logLine.innerHTML = `<span style="color: #94a3b8;">&gt;</span> ${message}`;
    } else if (message.startsWith("Running tool:")) {
        logLine.classList.add("tool");
        logLine.innerHTML = `<span style="color: #06b6d4;">[Tool]</span> ${message}`;
    } else {
        logLine.innerHTML = `<span>&gt;</span> ${message}`;
    }
    
    consoleLogs.appendChild(logLine);
    agentConsole.scrollTop = agentConsole.scrollHeight;
}

function clearAgentConsole() {
    consoleLogs.innerHTML = "";
    agentConsole.classList.add("hidden");
}

// --- RAG DOCUMENT UPLOADER ---
// Trigger browse
fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

// Drag & Drop event listeners
["dragenter", "dragover"].forEach(eventName => {
    dragArea.addEventListener(eventName, (e) => {
        e.preventDefault();
        dragArea.classList.add("dragover");
    }, false);
});

["dragleave", "drop"].forEach(eventName => {
    dragArea.addEventListener(eventName, (e) => {
        e.preventDefault();
        dragArea.classList.remove("dragover");
    }, false);
});

dragArea.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        handleFileUpload(files[0]);
    }
});

async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append("file", file);
    
    uploadStatus.className = "status-msg";
    uploadStatus.textContent = "Uploading and processing...";
    
    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            uploadStatus.className = "status-msg success";
            uploadStatus.textContent = result.message;
            loadUploadedFiles(); // Refresh files list
        } else {
            uploadStatus.className = "status-msg error";
            uploadStatus.textContent = result.detail || "Upload failed.";
        }
    } catch (error) {
        uploadStatus.className = "status-msg error";
        uploadStatus.textContent = "Network error occurred.";
    }
}

// --- FETCH UPLOADED FILES ---
async function loadUploadedFiles() {
    try {
        const response = await fetch("/files");
        const data = await response.json();
        
        uploadedFilesList.innerHTML = "";
        
        if (data.files.length === 0) {
            uploadedFilesList.innerHTML = '<li class="empty-list">No documents uploaded yet.</li>';
            return;
        }
        
        data.files.forEach(filename => {
            const li = document.createElement("li");
            li.innerHTML = `<i class="fa-solid fa-file-lines"></i> <span>${filename}</span>`;
            uploadedFilesList.appendChild(li);
        });
    } catch (e) {
        console.error("Failed to load uploaded files list.", e);
    }
}

// --- CHAT INTERACTION ---
chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
});

// Auto-grow input textarea
chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = (chatInput.scrollHeight) + "px";
});

// Shift+Enter handles new line, raw Enter submits
chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;
    
    // Check WebSocket state
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        appendErrorMessage("Cannot send. WebSocket is disconnected. Please wait for reconnection.");
        return;
    }
    
    // Determine selected LLM model
    let model = modelSelect.value;
    if (model === "custom") {
        model = customModelInput.value.trim() || "llama3";
    }
    
    // Append user message to UI
    appendUserBubble(query);
    clearAgentConsole();
    
    // Create socket payload
    const payload = {
        query: query,
        model: model,
        history: chatHistory
    };
    
    // Send to FastAPI socket
    socket.send(JSON.stringify(payload));
    
    // Add user message to history
    chatHistory.push({ role: "user", content: query });
    
    // Prepare temporary bot response bubble for streaming
    createBotBubblePlaceholder();
    
    // Reset inputs
    chatInput.value = "";
    chatInput.style.height = "auto";
}

function appendUserBubble(text) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message user-message";
    msgDiv.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-user"></i></div>
        <div class="message-content">${escapeHTML(text)}</div>
    `;
    chatMessages.appendChild(msgDiv);
    scrollChat();
}

function createBotBubblePlaceholder() {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message bot-message";
    msgDiv.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content streaming"></div>
    `;
    chatMessages.appendChild(msgDiv);
    currentBotMessageElement = msgDiv.querySelector(".message-content");
    scrollChat();
}

function appendBotToken(token) {
    if (currentBotMessageElement) {
        // Concatenate text
        currentBotMessageElement.textContent += token;
        
        // Clean markdown look slightly (very simple parser for UI demo)
        const rawText = currentBotMessageElement.textContent;
        currentBotMessageElement.innerHTML = formatMarkdown(rawText);
        
        scrollChat();
    }
}

function finalizeBotMessage() {
    if (currentBotMessageElement) {
        currentBotMessageElement.classList.remove("streaming");
        
        // Save chatbot response to history
        chatHistory.push({ role: "assistant", content: currentBotMessageElement.textContent });
        currentBotMessageElement = null;
        
        // Hide execution logs after a short delay
        setTimeout(() => {
            agentConsole.classList.add("hidden");
        }, 3000);
    }
}

function appendErrorMessage(text) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message bot-message";
    msgDiv.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-triangle-exclamation" style="color: #f43f5e;"></i></div>
        <div class="message-content" style="border-color: #f43f5e; color: #f43f5e; background-color: rgba(244,63,94,0.05);">
            <strong>Error:</strong> ${escapeHTML(text)}
        </div>
    `;
    chatMessages.appendChild(msgDiv);
    scrollChat();
}

// --- UTILITIES ---
function scrollChat() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHTML(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
    // Simple markdown renderer for code, lists, bold text
    let html = escapeHTML(text);
    
    // Replace new lines with breaks
    html = html.replace(/\n/g, "<br>");
    
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Inline code: `code`
    html = html.replace(/`(.*?)`/g, "<code>$1</code>");
    
    // Unordered lists: - item
    html = html.replace(/<br>-\s(.*?)(?=<br>|$)/g, "<li>$1</li>");
    // Wrap lists if list items exist
    if (html.includes("<li>")) {
        // Basic grouping logic for demo
    }
    
    return html;
}

// --- MODEL CONFIG INTERACTION ---
modelSelect.addEventListener("change", () => {
    if (modelSelect.value === "custom") {
        customModelGroup.classList.remove("hidden");
    } else {
        customModelGroup.classList.add("hidden");
    }
});

// --- CLEAR CHAT ---
btnClearChat.addEventListener("click", () => {
    chatMessages.innerHTML = `
        <div class="message bot-message">
            <div class="avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="message-content">
                Chat cleared! Ready for your next query.
            </div>
        </div>
    `;
    chatHistory = [];
    clearAgentConsole();
});

// --- INIT ---
connectWebSocket();
loadUploadedFiles();