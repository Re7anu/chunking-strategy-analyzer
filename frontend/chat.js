/**
 * Streaming Customer Support Chat
 */
function initChat() {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const clearBtn = document.getElementById('clear-chat');
  const submitBtn = document.getElementById('chat-submit-btn');

  // Clear Chat History
  clearBtn.addEventListener('click', () => {
    chatMessages.innerHTML = `
      <div class="message model">
        <div class="message-avatar">FA</div>
        <div class="message-bubble">
          <p>Welcome to <strong>NexusRAG</strong>. Ingest financial disclosures, statements, or PDF documentation, and query the assistant to generate audited reports based on scope.</p>
        </div>
      </div>
    `;
    chatHistory = [];
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const question = input.value.trim();
    if (!question) return;

    const strategy = 'all';
    const fiscalYear = null;
    const quarter = null;

    // 1. Add User Message to UI
    appendMessage('user', question);
    input.value = '';
    submitBtn.disabled = true;

    // 2. Add Loading Indicator
    const typingIndicator = appendTypingIndicator();
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 3. Setup streaming response bubble
    let modelBubble = null;
    let accumulatedResponse = '';

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ question, history: chatHistory, strategy, fiscalYear, quarter, threadId: currentThreadId })
      });

      if (!response.ok) {
        throw new Error('Failed to start chat streaming.');
      }

      // Remove typing indicator once stream starts
      removeTypingIndicator(typingIndicator);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // Create model message bubble in DOM
      const modelMessageDiv = createMessageContainer('model');
      modelBubble = modelMessageDiv.querySelector('.message-bubble');
      chatMessages.appendChild(modelMessageDiv);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        buffer = lines.pop() || '';

        for (const line of lines) {
          const cleanedLine = line.trim();
          if (!cleanedLine) continue;

          if (cleanedLine.startsWith('data: ')) {
            const dataStr = cleanedLine.slice(6);
            if (dataStr === '[DONE]') {
              break;
            }

            try {
              const data = JSON.parse(dataStr);
              if (data.text) {
                accumulatedResponse += data.text;
                modelBubble.innerHTML = renderMarkdown(accumulatedResponse);
                chatMessages.scrollTop = chatMessages.scrollHeight;
              } else if (data.error) {
                throw new Error(data.error);
              }
            } catch (err) {
              console.warn('Error parsing SSE event:', err, cleanedLine);
            }
          }
        }
      }

      const isFirstMessage = chatHistory.length === 0;

      // Save to chat state
      chatHistory.push({ role: 'user', content: question });
      chatHistory.push({ role: 'model', content: accumulatedResponse });

      if (isFirstMessage) {
        // Wait 400ms to allow backend database transaction commit to complete
        setTimeout(async () => {
          await loadThreads();
          const active = userThreads.find(t => t.id === currentThreadId);
          if (active) {
            const titleHeader = document.getElementById('chat-thread-title');
            if (titleHeader) titleHeader.textContent = active.title;
          }
        }, 400);
      }

    } catch (err) {
      console.error(err);
      removeTypingIndicator(typingIndicator);
      
      if (modelBubble) {
        modelBubble.innerHTML = `<span style="color: var(--error-color);"><i class="fa-solid fa-triangle-exclamation"></i> Error: ${err.message || 'Lost connection to server.'}</span>`;
      } else {
        appendMessage('model', `Failed to answer: ${err.message || 'Unable to connect to support service.'}`);
      }
    } finally {
      submitBtn.disabled = false;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  });
}

function appendMessage(role, text) {
  const chatMessages = document.getElementById('chat-messages');
  const container = createMessageContainer(role);
  const bubble = container.querySelector('.message-bubble');
  
  if (role === 'model') {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }

  chatMessages.appendChild(container);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return container;
}

function createMessageContainer(role) {
  const container = document.createElement('div');
  container.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  
  if (role === 'user') {
    const name = localStorage.getItem('username') || 'User';
    avatar.textContent = name.slice(0, 2).toUpperCase();
  } else {
    avatar.textContent = 'FA';
  }

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  container.appendChild(avatar);
  container.appendChild(bubble);
  return container;
}

function appendTypingIndicator() {
  const chatMessages = document.getElementById('chat-messages');
  const container = document.createElement('div');
  container.className = 'message model typing-container';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'FA';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = `
    <div class="typing-indicator">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>
  `;

  container.appendChild(avatar);
  container.appendChild(bubble);
  chatMessages.appendChild(container);
  return container;
}

function removeTypingIndicator(element) {
  if (element && element.parentNode) {
    element.parentNode.removeChild(element);
  }
}

/**
 * Persistence & Library UI Initializer
 */
function initPersistenceUI() {
  const newChatBtn = document.getElementById('new-chat-btn');
  const renameBtn = document.getElementById('edit-thread-title-btn');
  const refreshLibBtn = document.getElementById('refresh-library-btn');
  const attachDocBtn = document.getElementById('attach-doc-btn');
  const closeAttachBtn = document.getElementById('close-attach-modal');
  const attachModal = document.getElementById('attach-modal');

  const renameModal = document.getElementById('rename-thread-modal');
  const renameCancelBtn = document.getElementById('rename-cancel-btn');
  const renameConfirmBtn = document.getElementById('rename-confirm-btn');
  const renameInput = document.getElementById('rename-thread-input');

  if (newChatBtn) {
    newChatBtn.addEventListener('click', () => createNewThread());
  }

  if (renameBtn && renameModal && renameInput) {
    renameBtn.addEventListener('click', () => {
      if (!currentThreadId) return;
      const currentTitle = document.getElementById('chat-thread-title').textContent;
      renameInput.value = currentTitle;
      renameModal.style.display = 'flex';
      renameInput.focus();
    });

    if (renameCancelBtn) {
      renameCancelBtn.addEventListener('click', () => {
        renameModal.style.display = 'none';
      });
    }

    const submitRename = async () => {
      const newTitle = renameInput.value.trim();
      const currentTitle = document.getElementById('chat-thread-title').textContent;
      if (!newTitle || newTitle === currentTitle) {
        renameModal.style.display = 'none';
        return;
      }

      renameConfirmBtn.disabled = true;
      try {
        const res = await fetch(`/api/threads/${currentThreadId}`, {
          method: 'PATCH',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ title: newTitle })
        });
        if (!res.ok) throw new Error('Failed to rename thread');
        
        await loadThreads();
        const active = userThreads.find(t => t.id === currentThreadId);
        if (active) {
          document.getElementById('chat-thread-title').textContent = active.title;
        }
      } catch (err) {
        console.error('Error renaming thread:', err);
      } finally {
        renameConfirmBtn.disabled = false;
        renameModal.style.display = 'none';
      }
    };

    if (renameConfirmBtn) {
      renameConfirmBtn.addEventListener('click', submitRename);
    }

    renameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitRename();
      }
    });
  }

  if (refreshLibBtn) {
    refreshLibBtn.addEventListener('click', () => loadLibrary());
  }

  if (attachDocBtn) {
    attachDocBtn.addEventListener('click', () => showAttachModal());
  }

  if (closeAttachBtn) {
    closeAttachBtn.addEventListener('click', () => {
      attachModal.style.display = 'none';
    });
  }

  // Close modals when clicking outside card
  window.addEventListener('click', (e) => {
    if (e.target === attachModal) {
      attachModal.style.display = 'none';
    }
    if (e.target === renameModal) {
      renameModal.style.display = 'none';
    }
  });
}

/**
 * Fetch and Render Chat Threads List
 */
async function loadThreads() {
  const listContainer = document.getElementById('sidebar-threads-list');
  if (!listContainer || !token) return;

  try {
    const res = await fetch('/api/threads', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch threads');
    const data = await res.json();
    userThreads = data.threads || [];

    listContainer.innerHTML = '';
    if (userThreads.length === 0) {
      await createNewThread("Welcome Thread");
      return;
    }

    userThreads.forEach(t => {
      const activeClass = t.id === currentThreadId ? 'active' : '';
      const div = document.createElement('div');
      div.className = `thread-item ${activeClass}`;
      div.setAttribute('data-id', t.id);
      
      div.innerHTML = `
        <span class="thread-title-text-span"><i class="fa-regular fa-message" style="margin-right: 0.35rem;"></i> ${escapeHTML(t.title)}</span>
        <button class="delete-thread-btn" title="Delete Chat"><i class="fa-solid fa-trash"></i></button>
      `;

      // Select thread on click
      div.addEventListener('click', (e) => {
        if (e.target.closest('.delete-thread-btn')) {
          e.stopPropagation();
          deleteThread(t.id);
        } else {
          selectThread(t.id);
        }
      });

      listContainer.appendChild(div);
    });

    if (!currentThreadId && userThreads.length > 0) {
      selectThread(userThreads[0].id);
    }
  } catch (err) {
    console.error('Error loading threads:', err);
    listContainer.innerHTML = `<div class="thread-loading-item" style="color: var(--error-color);">Failed to load conversations.</div>`;
  }
}

/**
 * Create a new Thread
 */
async function createNewThread(title = "New Chat") {
  if (!token) return;
  try {
    const res = await fetch('/api/threads', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ title })
    });
    if (!res.ok) throw new Error('Failed to create thread');
    const data = await res.json();
    
    currentThreadId = data.thread.id;
    await loadThreads();
    selectThread(currentThreadId);
  } catch (err) {
    console.error('Error creating thread:', err);
  }
}

/**
 * Select Active Thread & Load Messages
 */
async function selectThread(threadId) {
  currentThreadId = threadId;
  
  document.querySelectorAll('.thread-item').forEach(item => {
    item.classList.remove('active');
    if (item.getAttribute('data-id') === threadId) {
      item.classList.add('active');
    }
  });

  const activeThread = userThreads.find(t => t.id === threadId);
  const titleHeader = document.getElementById('chat-thread-title');
  if (titleHeader && activeThread) {
    titleHeader.textContent = activeThread.title;
  }

  await loadThreadMessages(threadId);
  await loadAttachedDocuments(threadId);
}

/**
 * Fetch and Render Thread Messages
 */
async function loadThreadMessages(threadId) {
  const chatMessages = document.getElementById('chat-messages');
  if (!chatMessages || !token) return;

  try {
    const res = await fetch(`/api/threads/${threadId}/messages`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to load thread messages');
    const data = await res.json();
    const messages = data.messages || [];
    
    chatHistory = messages;

    chatMessages.innerHTML = '';
    if (messages.length === 0) {
      chatMessages.innerHTML = `
        <div class="message model">
          <div class="message-avatar">FA</div>
          <div class="message-bubble">
            <p>Welcome to <strong>NexusRAG</strong>. Ingest financial disclosures, statements, or PDF documentation, and query the assistant to generate audited reports based on scope.</p>
          </div>
        </div>
      `;
      return;
    }

    messages.forEach(msg => {
      appendMessage(msg.role, msg.content);
    });
  } catch (err) {
    console.error('Error rendering messages:', err);
  }
}

/**
 * Delete a Chat Thread
 */
async function deleteThread(threadId) {
  if (!token || !confirm('Are you sure you want to delete this conversation?')) return;
  try {
    const res = await fetch(`/api/threads/${threadId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to delete thread');
    
    if (currentThreadId === threadId) {
      currentThreadId = null;
    }
    await loadThreads();
  } catch (err) {
    console.error('Error deleting thread:', err);
  }
}



/**
 * Fetch and Render Document Attachments on the Chat View
 */
async function loadAttachedDocuments(threadId) {
  const container = document.getElementById('attached-docs-list');
  if (!container || !token) return;

  try {
    const res = await fetch(`/api/threads/${threadId}/documents`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch attachments');
    const data = await res.json();
    attachedDocs = data.documents || [];

    renderAttachedDocuments();
  } catch (err) {
    console.error('Error loading attachments:', err);
  }
}

function renderAttachedDocuments() {
  const container = document.getElementById('attached-docs-list');
  if (!container) return;

  container.innerHTML = '';
  if (attachedDocs.length === 0) {
    container.innerHTML = `<span style="font-size: 0.8rem; color: var(--text-muted); font-style: italic;">No documents attached. Search queries will scan your entire library.</span>`;
    return;
  }

  attachedDocs.forEach(d => {
    const pill = document.createElement('div');
    pill.className = 'attached-doc-pill';
    
    pill.innerHTML = `
      <i class="fa-solid fa-file-pdf"></i>
      <span>${escapeHTML(d.filename)}</span>
      <button class="detach-doc-x" title="Detach Document">&times;</button>
    `;

    pill.querySelector('.detach-doc-x').addEventListener('click', async (e) => {
      e.stopPropagation();
      await detachDocument(d.id);
    });

    container.appendChild(pill);
  });
}

/**
 * Detach Document from Chat
 */
async function detachDocument(docId) {
  if (!currentThreadId || !token) return;
  try {
    const res = await fetch(`/api/threads/${currentThreadId}/documents/${docId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to detach document');
    
    await loadAttachedDocuments(currentThreadId);
  } catch (err) {
    console.error('Error detaching document:', err);
  }
}

/**
 * Show Attach Document Modal checkbox rows
 */
async function showAttachModal() {
  const modal = document.getElementById('attach-modal');
  const listContainer = document.getElementById('modal-library-list');
  if (!modal || !listContainer || !currentThreadId || !token) return;

  try {
    const res = await fetch('/api/documents', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    libraryDocs = data.documents || [];

    listContainer.innerHTML = '';
    modal.style.display = 'flex';

    if (libraryDocs.length === 0) {
      listContainer.innerHTML = `<p style="font-size: 0.85rem; color: var(--text-muted); text-align: center; padding: 1.5rem 0;">No documents in your library. Please go to "Ingest & Library" to index documents first.</p>`;
      return;
    }

    libraryDocs.forEach(d => {
      const isAttached = attachedDocs.some(ad => ad.id === d.id);
      
      const row = document.createElement('div');
      row.className = 'modal-library-row';
      
      const fileIcon = d.filename.endsWith('.pdf') ? 'fa-file-pdf' : 'fa-file-lines';

      row.innerHTML = `
        <label class="modal-library-label">
          <input type="checkbox" class="modal-library-checkbox" ${isAttached ? 'checked' : ''}>
          <i class="fa-solid ${fileIcon}" style="margin-right: 0.25rem;"></i>
          <span>${escapeHTML(d.filename)}</span>
        </label>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Pages: ${d.pagesCount}</span>
      `;

      const checkbox = row.querySelector('.modal-library-checkbox');
      checkbox.addEventListener('change', async () => {
        checkbox.disabled = true;
        try {
          if (checkbox.checked) {
            await fetch(`/api/threads/${currentThreadId}/documents`, {
              method: 'POST',
              headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
              },
              body: JSON.stringify({ documentId: d.id })
            });
          } else {
            await fetch(`/api/threads/${currentThreadId}/documents/${d.id}`, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${token}` }
            });
          }
          await loadAttachedDocuments(currentThreadId);
        } catch (err) {
          console.error('Error toggling attachment:', err);
          checkbox.checked = !checkbox.checked;
        } finally {
          checkbox.disabled = false;
        }
      });

      listContainer.appendChild(row);
    });

  } catch (err) {
    console.error('Error rendering attachment list:', err);
  }
}
