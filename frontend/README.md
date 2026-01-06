# QuantumDev AI - Web Interface

## Overview

A modern, ChatGPT/Claude-like web interface for QuantumDev AI, featuring:

- **Modern UI/UX**: Clean, responsive design with dark/light mode
- **Streaming Responses**: Real-time streaming of AI responses with Server-Sent Events
- **Auto Web Search**: Automatic web search detection and integration
- **File Upload**: Support for images, PDFs, and documents with OCR
- **Conversation Management**: Persistent conversation history with localStorage
- **Settings Panel**: Customizable model parameters, temperature, and features
- **Multi-modal Support**: Text, code, images, and artifacts
- **Source Citations**: Display web sources with clickable links

## Features

### 🎨 User Interface

- **Welcome Screen**: Shows capabilities and example prompts
- **Message Display**: Clean message bubbles with user/assistant distinction
- **Code Highlighting**: Syntax highlighting for code blocks using highlight.js
- **Markdown Support**: Full markdown rendering with marked.js and DOMPurify
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### 🚀 Core Functionality

1. **Streaming Chat**
   - Real-time response streaming using SSE
   - Progressive rendering of responses
   - Typing indicators and web search indicators

2. **Auto Web Search**
   - Automatic detection of queries requiring web search
   - Visual indicators when web search is active
   - Source citations with clickable links

3. **File Upload**
   - Support for multiple file types (images, PDFs, documents)
   - File size validation (max 10MB per file)
   - Visual file chips with remove functionality

4. **Conversation Management**
   - Persistent conversation history in localStorage
   - Create new chats
   - Switch between conversations
   - Export conversations to Markdown

5. **Settings**
   - Model selection
   - Temperature control (0.0 - 2.0)
   - Max tokens configuration
   - Toggle auto web search
   - Toggle conversational memory
   - Toggle streaming mode

### 🎯 Advanced Features

- **Dark/Light Mode**: Toggle between themes with persistent preference
- **Example Prompts**: Quick-start prompts for common use cases
- **Message Actions**: Copy and regenerate message buttons
- **Export Conversations**: Download chat history as Markdown
- **Responsive Sidebar**: Collapsible conversation history

## Architecture

### Frontend Structure

```
frontend/
├── templates/
│   └── chat.html          # Main HTML template
└── static/
    ├── css/
    │   └── chat.css       # Styles for chat interface
    └── js/
        └── chat.js        # Chat interface JavaScript
```

### Backend Integration

The web interface integrates with existing QuantumDev backend endpoints:

- `GET /` - Serves the chat interface
- `POST /chat` - Non-streaming chat endpoint
- `POST /chat/stream` - Streaming chat endpoint (SSE)
- `POST /files/upload` - File upload endpoint

### Key Technologies

- **Frontend**:
  - Vanilla JavaScript (ES6+)
  - CSS3 with CSS Variables for theming
  - marked.js for Markdown rendering
  - DOMPurify for XSS protection
  - highlight.js for code syntax highlighting
  - Font Awesome for icons

- **Backend**:
  - FastAPI for serving static files and templates
  - Jinja2 for template rendering
  - Server-Sent Events (SSE) for streaming

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Web Interface
WEB_INTERFACE_ENABLED=true
WEB_INTERFACE_TITLE=QuantumDev AI
WEB_INTERFACE_SUBTITLE=Il tuo assistente AI personale senza censura

# Streaming
STREAMING_ENABLED=true
STREAMING_CHUNK_SIZE=256

# File Upload
FILE_UPLOAD_ENABLED=true
FILE_UPLOAD_MAX_SIZE=10485760     # 10MB
FILE_UPLOAD_ALLOWED_EXTENSIONS=.pdf,.txt,.doc,.docx,.jpg,.jpeg,.png,.gif

# Auto Web Search (already configured)
AUTO_SEARCH_ENABLED=true
AUTO_SEARCH_CONFIDENCE_THRESHOLD=0.7
```

## Usage

### Starting the Server

```bash
# Start the FastAPI server
uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000

# Or with auto-reload for development
uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000 --reload
```

### Accessing the Interface

Open your browser and navigate to:
```
http://localhost:8000/
```

### Example Interactions

1. **Simple Chat**
   - Type a message and press Enter or click Send
   - Watch the response stream in real-time

2. **Web Search**
   - Ask "What's the current price of Bitcoin?"
   - The system automatically detects the need for web search
   - Watch the web search indicator appear
   - See sources listed below the response

3. **File Upload**
   - Click the paperclip icon
   - Select one or more files (images, PDFs, documents)
   - Files are displayed as chips
   - Send your message with the attached files

4. **Settings**
   - Click the settings button in sidebar
   - Adjust temperature, max tokens, etc.
   - Toggle features like auto search and streaming
   - Click Save

5. **Export**
   - Click the download icon in header
   - Conversation is exported as Markdown file

## API Endpoints Used

### GET /

Main chat interface endpoint. Returns the HTML page.

### POST /chat

Standard chat endpoint without streaming.

**Request:**
```json
{
  "text": "Your message here",
  "source": "web",
  "source_id": "chat-123456789",
  "messages": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Previous response"}
  ],
  "auto_search": true,
  "temperature": 0.7,
  "max_tokens": 2048
}
```

**Response:**
```json
{
  "response": "Assistant response",
  "sources": [
    {
      "url": "https://example.com",
      "title": "Example Source"
    }
  ]
}
```

### POST /chat/stream

Streaming chat endpoint using Server-Sent Events.

**Request:** Same as `/chat`

**Response:** SSE stream with events:
```
data: {"type": "thinking", "content": "Analyzing query..."}
data: {"type": "token", "content": "Response "}
data: {"type": "token", "content": "text "}
data: {"type": "sources", "sources": [...]}
data: {"type": "done"}
data: [DONE]
```

### POST /files/upload

File upload endpoint.

**Request:** multipart/form-data with files

**Response:**
```json
{
  "urls": ["file1_url", "file2_url"],
  "count": 2
}
```

## Customization

### Theming

Edit `frontend/static/css/chat.css` and modify CSS variables:

```css
:root {
    --primary-color: #10a37f;
    --primary-hover: #0d8c6d;
    --background: #ffffff;
    --text-primary: #0d0d0d;
    /* ... more variables */
}
```

### Branding

Edit `frontend/templates/chat.html`:

```html
<title>Your Brand Name</title>
<h1>Welcome to Your AI</h1>
```

### Example Prompts

Modify the example prompts in `chat.html`:

```html
<button class="example-prompt">Your custom prompt here</button>
```

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Performance

- **First Load**: ~2MB (includes libraries from CDN)
- **Subsequent Loads**: Cached static assets
- **Streaming Latency**: <100ms per token
- **File Upload**: Supports up to 10MB per file

## Security

- **XSS Protection**: DOMPurify sanitizes all markdown rendering
- **CORS**: Backend handles CORS headers
- **Rate Limiting**: Backend implements rate limiting
- **File Upload**: File type and size validation

## Troubleshooting

### Interface Not Loading

1. Check if static files are mounted:
   ```
   ✓ [FRONTEND] Static files mounted from /path/to/frontend/static
   ```

2. Check if templates directory exists:
   ```
   frontend/templates/chat.html
   ```

### Streaming Not Working

1. Ensure `/chat/stream` endpoint exists in backend
2. Check browser console for SSE connection errors
3. Verify `STREAMING_ENABLED=true` in `.env`

### Auto Web Search Not Triggering

1. Check `AUTO_SEARCH_ENABLED=true` in `.env`
2. Verify auto search detector is configured
3. Check logs for auto search detection

### File Upload Failing

1. Ensure `/files/upload` endpoint exists
2. Check file size (max 10MB)
3. Verify file type is allowed
4. Check backend logs for upload errors

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Start with auto-reload
uvicorn backend.quantum_api:app --reload --port 8000

# Access at http://localhost:8000
```

### Making Changes

1. **HTML Changes**: Edit `frontend/templates/chat.html`
2. **Styling**: Edit `frontend/static/css/chat.css`
3. **Functionality**: Edit `frontend/static/js/chat.js`
4. **Refresh browser** to see changes (with --reload)

## Future Enhancements

- [ ] Voice input/output
- [ ] Image generation integration
- [ ] Multi-user support with authentication
- [ ] Real-time collaboration
- [ ] Mobile app (PWA)
- [ ] Plugin system for extensions
- [ ] Advanced search in conversation history
- [ ] Conversation sharing and export
- [ ] Custom system prompts per conversation
- [ ] Keyboard shortcuts

## Credits

Built with:
- FastAPI
- Jinja2
- marked.js
- DOMPurify
- highlight.js
- Font Awesome

## License

Same as QuantumDev main project.
