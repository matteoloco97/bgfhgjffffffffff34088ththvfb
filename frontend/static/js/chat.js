// QuantumDev AI - Chat Interface JavaScript

class ChatInterface {
    constructor() {
        this.currentChatId = null;
        this.conversations = this.loadConversations();
        this.settings = this.loadSettings();
        this.attachedFiles = [];
        this.currentEventSource = null;
        
        this.initializeElements();
        this.attachEventListeners();
        this.applySavedTheme();
        this.renderChatHistory();
    }

    initializeElements() {
        // Main elements
        this.sidebar = document.getElementById('sidebar');
        this.chatContainer = document.getElementById('chatContainer');
        this.messagesContainer = document.getElementById('messages');
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.messageInput = document.getElementById('messageInput');
        this.chatForm = document.getElementById('chatForm');
        this.sendBtn = document.getElementById('sendBtn');
        
        // Indicators
        this.typingIndicator = document.getElementById('typingIndicator');
        this.webSearchIndicator = document.getElementById('webSearchIndicator');
        
        // File handling
        this.fileInput = document.getElementById('fileInput');
        this.attachedFilesContainer = document.getElementById('attachedFiles');
        
        // Modals
        this.settingsModal = document.getElementById('settingsModal');
    }

    attachEventListeners() {
        // Chat form submission
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = this.messageInput.scrollHeight + 'px';
        });

        // Enter key to send (Shift+Enter for new line)
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Sidebar toggle
        document.getElementById('sidebarToggle').addEventListener('click', () => {
            this.sidebar.classList.toggle('collapsed');
            this.sidebar.classList.toggle('show');
        });

        // New chat
        document.getElementById('newChatBtn').addEventListener('click', () => {
            this.createNewChat();
        });

        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => {
            this.toggleTheme();
        });

        // Settings
        document.getElementById('settingsBtn').addEventListener('click', () => {
            this.openSettings();
        });

        document.getElementById('closeSettings').addEventListener('click', () => {
            this.closeSettings();
        });

        document.getElementById('saveSettings').addEventListener('click', () => {
            this.saveSettingsFromModal();
        });

        document.getElementById('resetSettings').addEventListener('click', () => {
            this.resetSettings();
        });

        // Temperature slider
        document.getElementById('temperatureSlider').addEventListener('input', (e) => {
            document.getElementById('temperatureValue').textContent = e.target.value;
        });

        // File attachment
        document.getElementById('attachBtn').addEventListener('click', () => {
            this.fileInput.click();
        });

        this.fileInput.addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files);
        });

        // Export conversation
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.exportConversation();
        });

        // Clear chat
        document.getElementById('clearBtn').addEventListener('click', () => {
            if (confirm('Sei sicuro di voler cancellare questa conversazione?')) {
                this.clearCurrentChat();
            }
        });

        // Example prompts
        document.querySelectorAll('.example-prompt').forEach(btn => {
            btn.addEventListener('click', () => {
                this.messageInput.value = btn.textContent;
                this.messageInput.focus();
            });
        });
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message && this.attachedFiles.length === 0) return;

        // Create or get current chat
        if (!this.currentChatId) {
            this.createNewChat();
        }

        // Hide welcome screen
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = 'none';
        }

        // Add user message to UI
        this.addMessageToUI('user', message, this.attachedFiles);

        // Clear input and files
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        const files = [...this.attachedFiles];
        this.attachedFiles = [];
        this.updateAttachedFilesUI();

        // Disable send button
        this.sendBtn.disabled = true;

        try {
            // Handle file uploads first if present
            let uploadedFileUrls = [];
            if (files.length > 0) {
                uploadedFileUrls = await this.uploadFiles(files);
            }

            // Check if streaming is enabled
            if (this.settings.streaming) {
                await this.sendStreamingMessage(message, uploadedFileUrls);
            } else {
                await this.sendRegularMessage(message, uploadedFileUrls);
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessageToUI('assistant', '❌ Si è verificato un errore. Riprova.');
        } finally {
            this.sendBtn.disabled = false;
            this.messageInput.focus();
        }
    }

    async sendStreamingMessage(message, fileUrls = []) {
        // Show typing indicator
        this.typingIndicator.style.display = 'flex';

        // Create assistant message container
        const messageId = 'msg-' + Date.now();
        const messageElement = this.createMessageElement('assistant', '', [], messageId);
        this.messagesContainer.appendChild(messageElement);
        const contentElement = messageElement.querySelector('.message-body');

        // Prepare payload
        const payload = {
            text: message,
            source: 'web',
            source_id: this.currentChatId || 'default',
            messages: this.buildMessagesArray(),
            streaming: true,
            auto_search: this.settings.autoSearch,
            temperature: this.settings.temperature,
            max_tokens: this.settings.maxTokens,
        };

        if (fileUrls.length > 0) {
            payload.file_urls = fileUrls;
        }

        try {
            // Close any existing event source
            if (this.currentEventSource) {
                this.currentEventSource.close();
            }

            // Use Server-Sent Events for streaming
            const response = await fetch('/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullResponse = '';

            while (true) {
                const { done, value } = await reader.read();
                
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        
                        if (data === '[DONE]') {
                            break;
                        }

                        try {
                            const parsed = JSON.parse(data);
                            
                            if (parsed.type === 'thinking') {
                                // Show web search indicator
                                if (parsed.content.includes('web') || parsed.content.includes('ricerca')) {
                                    this.webSearchIndicator.style.display = 'flex';
                                }
                            } else if (parsed.type === 'token') {
                                fullResponse += parsed.content;
                                contentElement.innerHTML = this.renderMarkdown(fullResponse);
                                this.highlightCode(contentElement);
                                this.scrollToBottom();
                            } else if (parsed.type === 'sources') {
                                this.addSourcesToMessage(messageElement, parsed.sources);
                            } else if (parsed.type === 'done') {
                                // Hide indicators
                                this.webSearchIndicator.style.display = 'none';
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e);
                        }
                    }
                }
            }

            // Save to conversation history
            this.saveMessageToHistory('assistant', fullResponse);

        } catch (error) {
            console.error('Streaming error:', error);
            contentElement.innerHTML = '❌ Errore durante la ricezione della risposta.';
        } finally {
            this.typingIndicator.style.display = 'none';
            this.webSearchIndicator.style.display = 'none';
            this.scrollToBottom();
        }
    }

    async sendRegularMessage(message, fileUrls = []) {
        this.typingIndicator.style.display = 'flex';

        const payload = {
            text: message,
            source: 'web',
            source_id: this.currentChatId || 'default',
            messages: this.buildMessagesArray(),
            auto_search: this.settings.autoSearch,
            temperature: this.settings.temperature,
            max_tokens: this.settings.maxTokens,
        };

        if (fileUrls.length > 0) {
            payload.file_urls = fileUrls;
        }

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }

            const assistantMessage = data.response || data.answer || 'Nessuna risposta ricevuta.';
            const sources = data.sources || [];

            this.addMessageToUI('assistant', assistantMessage, [], sources);
            this.saveMessageToHistory('assistant', assistantMessage);

        } catch (error) {
            console.error('Error:', error);
            this.addMessageToUI('assistant', '❌ Si è verificato un errore: ' + error.message);
        } finally {
            this.typingIndicator.style.display = 'none';
        }
    }

    async uploadFiles(files) {
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file.file);
        });

        try {
            const response = await fetch('/files/upload', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error('File upload failed');
            }

            const data = await response.json();
            return data.urls || [];
        } catch (error) {
            console.error('Upload error:', error);
            return [];
        }
    }

    handleFileSelect(files) {
        Array.from(files).forEach(file => {
            // Check file size (max 10MB)
            if (file.size > 10 * 1024 * 1024) {
                alert(`Il file ${file.name} è troppo grande. Massimo 10MB.`);
                return;
            }

            this.attachedFiles.push({
                name: file.name,
                size: file.size,
                type: file.type,
                file: file,
            });
        });

        this.updateAttachedFilesUI();
        this.fileInput.value = '';
    }

    updateAttachedFilesUI() {
        if (this.attachedFiles.length === 0) {
            this.attachedFilesContainer.style.display = 'none';
            this.attachedFilesContainer.innerHTML = '';
            return;
        }

        this.attachedFilesContainer.style.display = 'flex';
        this.attachedFilesContainer.innerHTML = this.attachedFiles.map((file, index) => `
            <div class="file-chip">
                <i class="fas fa-file"></i>
                <span>${file.name}</span>
                <button type="button" class="remove-file" data-index="${index}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');

        // Attach remove handlers
        this.attachedFilesContainer.querySelectorAll('.remove-file').forEach(btn => {
            btn.addEventListener('click', () => {
                const index = parseInt(btn.dataset.index);
                this.attachedFiles.splice(index, 1);
                this.updateAttachedFilesUI();
            });
        });
    }

    addMessageToUI(role, content, files = [], sources = []) {
        const messageElement = this.createMessageElement(role, content, files, null, sources);
        this.messagesContainer.appendChild(messageElement);
        this.scrollToBottom();

        // Save to conversation
        this.saveMessageToHistory(role, content);
    }

    createMessageElement(role, content, files = [], id = null, sources = []) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        if (id) messageDiv.id = id;

        const avatar = role === 'user' 
            ? '<i class="fas fa-user"></i>' 
            : '<i class="fas fa-robot"></i>';

        const sender = role === 'user' ? 'Tu' : 'Assistente';
        const time = new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

        let filesHTML = '';
        if (files.length > 0) {
            filesHTML = `
                <div class="message-files">
                    ${files.map(f => `<span class="file-chip"><i class="fas fa-file"></i> ${f.name}</span>`).join('')}
                </div>
            `;
        }

        let sourcesHTML = '';
        if (sources.length > 0) {
            sourcesHTML = this.createSourcesHTML(sources);
        }

        messageDiv.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-sender">${sender}</span>
                    <span class="message-time">${time}</span>
                </div>
                ${filesHTML}
                <div class="message-body">${this.renderMarkdown(content)}</div>
                ${sourcesHTML}
                ${role === 'assistant' ? this.createMessageActions() : ''}
            </div>
        `;

        // Highlight code blocks
        this.highlightCode(messageDiv);

        return messageDiv;
    }

    createSourcesHTML(sources) {
        if (!sources || sources.length === 0) return '';

        return `
            <div class="message-sources">
                <h4><i class="fas fa-link"></i> Fonti</h4>
                <div class="source-list">
                    ${sources.map((source, i) => `
                        <div class="source-item">
                            <span>${i + 1}.</span>
                            <a href="${source.url}" target="_blank" rel="noopener noreferrer">
                                ${source.title || source.url}
                            </a>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    addSourcesToMessage(messageElement, sources) {
        const contentDiv = messageElement.querySelector('.message-content');
        const existingSources = contentDiv.querySelector('.message-sources');
        
        if (existingSources) {
            existingSources.remove();
        }

        const sourcesHTML = this.createSourcesHTML(sources);
        const actionsDiv = contentDiv.querySelector('.message-actions');
        
        if (actionsDiv) {
            actionsDiv.insertAdjacentHTML('beforebegin', sourcesHTML);
        } else {
            contentDiv.insertAdjacentHTML('beforeend', sourcesHTML);
        }
    }

    createMessageActions() {
        return `
            <div class="message-actions">
                <button class="action-btn copy-btn">
                    <i class="fas fa-copy"></i>
                    Copia
                </button>
                <button class="action-btn regenerate-btn">
                    <i class="fas fa-redo"></i>
                    Rigenera
                </button>
            </div>
        `;
    }

    renderMarkdown(text) {
        if (!text) return '';
        
        // Configure marked
        marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false,
        });

        const html = marked.parse(text);
        return DOMPurify.sanitize(html);
    }

    highlightCode(element) {
        element.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    buildMessagesArray() {
        if (!this.currentChatId || !this.conversations[this.currentChatId]) {
            return [];
        }

        const conversation = this.conversations[this.currentChatId];
        return conversation.messages.map(msg => ({
            role: msg.role,
            content: msg.content,
        }));
    }

    createNewChat() {
        const chatId = 'chat-' + Date.now();
        this.currentChatId = chatId;
        
        this.conversations[chatId] = {
            id: chatId,
            title: 'Nuova conversazione',
            messages: [],
            createdAt: new Date().toISOString(),
        };

        this.saveConversations();
        this.renderChatHistory();
        this.clearMessagesUI();
        
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = 'flex';
        }
    }

    clearMessagesUI() {
        this.messagesContainer.innerHTML = '';
    }

    clearCurrentChat() {
        if (this.currentChatId && this.conversations[this.currentChatId]) {
            delete this.conversations[this.currentChatId];
            this.saveConversations();
            this.renderChatHistory();
            this.createNewChat();
        }
    }

    saveMessageToHistory(role, content) {
        if (!this.currentChatId) return;

        const conversation = this.conversations[this.currentChatId];
        if (!conversation) return;

        conversation.messages.push({
            role,
            content,
            timestamp: new Date().toISOString(),
        });

        // Update title from first user message
        if (conversation.messages.length === 1 && role === 'user') {
            conversation.title = content.substring(0, 50) + (content.length > 50 ? '...' : '');
        }

        this.saveConversations();
        this.renderChatHistory();
    }

    renderChatHistory() {
        const historyContainer = document.getElementById('chatHistory');
        const sortedChats = Object.values(this.conversations)
            .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

        historyContainer.innerHTML = sortedChats.map(chat => `
            <div class="chat-item ${chat.id === this.currentChatId ? 'active' : ''}" data-chat-id="${chat.id}">
                ${chat.title}
            </div>
        `).join('');

        // Attach click handlers
        historyContainer.querySelectorAll('.chat-item').forEach(item => {
            item.addEventListener('click', () => {
                this.loadChat(item.dataset.chatId);
            });
        });
    }

    loadChat(chatId) {
        if (!this.conversations[chatId]) return;

        this.currentChatId = chatId;
        this.clearMessagesUI();
        
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = 'none';
        }

        const conversation = this.conversations[chatId];
        conversation.messages.forEach(msg => {
            const messageElement = this.createMessageElement(msg.role, msg.content);
            this.messagesContainer.appendChild(messageElement);
        });

        this.renderChatHistory();
        this.scrollToBottom();
    }

    exportConversation() {
        if (!this.currentChatId || !this.conversations[this.currentChatId]) {
            alert('Nessuna conversazione da esportare');
            return;
        }

        const conversation = this.conversations[this.currentChatId];
        const markdown = this.conversationToMarkdown(conversation);
        
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conversazione-${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }

    conversationToMarkdown(conversation) {
        let markdown = `# ${conversation.title}\n\n`;
        markdown += `Data: ${new Date(conversation.createdAt).toLocaleString('it-IT')}\n\n`;
        markdown += '---\n\n';

        conversation.messages.forEach(msg => {
            const sender = msg.role === 'user' ? '👤 Utente' : '🤖 Assistente';
            markdown += `## ${sender}\n\n${msg.content}\n\n---\n\n`;
        });

        return markdown;
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);

        const icon = document.querySelector('#themeToggle i');
        icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }

    applySavedTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        
        const icon = document.querySelector('#themeToggle i');
        icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }

    openSettings() {
        this.settingsModal.style.display = 'flex';
        
        // Populate current settings
        document.getElementById('modelSelect').value = this.settings.model;
        document.getElementById('temperatureSlider').value = this.settings.temperature;
        document.getElementById('temperatureValue').textContent = this.settings.temperature;
        document.getElementById('maxTokensInput').value = this.settings.maxTokens;
        document.getElementById('autoSearchToggle').checked = this.settings.autoSearch;
        document.getElementById('memoryToggle').checked = this.settings.memory;
        document.getElementById('streamingToggle').checked = this.settings.streaming;
    }

    closeSettings() {
        this.settingsModal.style.display = 'none';
    }

    saveSettingsFromModal() {
        this.settings = {
            model: document.getElementById('modelSelect').value,
            temperature: parseFloat(document.getElementById('temperatureSlider').value),
            maxTokens: parseInt(document.getElementById('maxTokensInput').value),
            autoSearch: document.getElementById('autoSearchToggle').checked,
            memory: document.getElementById('memoryToggle').checked,
            streaming: document.getElementById('streamingToggle').checked,
        };

        this.saveSettings();
        this.closeSettings();
    }

    resetSettings() {
        this.settings = this.getDefaultSettings();
        this.saveSettings();
        this.openSettings(); // Refresh the modal
    }

    getDefaultSettings() {
        return {
            model: 'deepseek-qwen-32b',
            temperature: 0.7,
            maxTokens: 2048,
            autoSearch: true,
            memory: true,
            streaming: true,
        };
    }

    loadSettings() {
        const saved = localStorage.getItem('chatSettings');
        return saved ? JSON.parse(saved) : this.getDefaultSettings();
    }

    saveSettings() {
        localStorage.setItem('chatSettings', JSON.stringify(this.settings));
    }

    loadConversations() {
        const saved = localStorage.getItem('conversations');
        return saved ? JSON.parse(saved) : {};
    }

    saveConversations() {
        localStorage.setItem('conversations', JSON.stringify(this.conversations));
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
        }, 100);
    }
}

// Initialize the chat interface when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ChatInterface();
});
