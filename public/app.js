// Application State
let chatHistory = [];

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initIngestionMode();
  initIngestion();
  initSearchSandbox();
  initChat();
  initCompareDashboard();
});

/**
 * Tab Navigation Setup
 */
function initTabs() {
  const navBtns = document.querySelectorAll('.nav-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTabId = btn.getAttribute('data-tab');

      // Update button state
      navBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // Update visible tab content
      tabContents.forEach(tab => {
        tab.classList.remove('active');
        if (tab.id === targetTabId) {
          tab.classList.add('active');
        }
      });
    });
  });
}

/**
 * Ingestion Form Mode Toggles & Param Visibility
 */
function initIngestionMode() {
  const radioButtons = document.querySelectorAll('input[name="ingest-method"]');
  const textInputGroup = document.getElementById('text-input-group');
  const pdfInputGroup = document.getElementById('pdf-input-group');
  const contentTextarea = document.getElementById('ingest-content');
  const fileInput = document.getElementById('ingest-file');

  radioButtons.forEach(radio => {
    radio.addEventListener('change', (e) => {
      if (e.target.value === 'pdf') {
        textInputGroup.style.display = 'none';
        pdfInputGroup.style.display = 'block';
        contentTextarea.removeAttribute('required');
      } else {
        textInputGroup.style.display = 'block';
        pdfInputGroup.style.display = 'none';
        contentTextarea.setAttribute('required', 'required');
      }
    });
  });

  // Strategy change handler to toggle threshold input
  const strategySelect = document.getElementById('ingest-strategy');
  const thresholdGroup = document.getElementById('semantic-threshold-group');
  const chunkSizeInput = document.getElementById('ingest-chunk-size');
  const overlapInput = document.getElementById('ingest-chunk-overlap');
  const overlapGroup = document.getElementById('chunk-overlap-group');

  strategySelect.addEventListener('change', (e) => {
    const strategy = e.target.value;
    
    // Toggle threshold input visibility
    if (strategy === 'semantic') {
      thresholdGroup.style.display = 'block';
    } else {
      thresholdGroup.style.display = 'none';
    }

    // Toggle overlap field (page-based doesn't use character overlap in the same way)
    if (strategy === 'page-based') {
      overlapGroup.style.display = 'none';
      chunkSizeInput.value = '1500'; // Default higher page size
    } else {
      overlapGroup.style.display = 'block';
      if (chunkSizeInput.value === '1500') {
        chunkSizeInput.value = '1000'; // Reset to standard chunk size
      }
    }
  });

  // PDF Drag & Drop Setup
  const dropZone = document.getElementById('file-drop-zone');
  const fileNameDisplay = document.getElementById('file-name-display');

  // Trigger file browser on click
  dropZone.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      fileNameDisplay.textContent = `Selected: ${fileInput.files[0].name} (${formatBytes(fileInput.files[0].size)})`;
      dropZone.classList.add('has-file');
    } else {
      fileNameDisplay.textContent = 'No file selected';
      dropZone.classList.remove('has-file');
    }
  });

  // Drag & drop highlights
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add('highlight');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove('highlight');
    }, false);
  });

  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0 && files[0].type === 'application/pdf') {
      fileInput.files = files;
      fileNameDisplay.textContent = `Selected: ${files[0].name} (${formatBytes(files[0].size)})`;
      dropZone.classList.add('has-file');
    }
  });

  // Ingest all strategies checkbox toggle listener
  const allStrategiesCheckbox = document.getElementById('ingest-all-strategies');
  const singleStrategyGrid = document.getElementById('single-strategy-config-grid');
  const multiStrategyGrid = document.getElementById('multi-strategy-config-grid');

  allStrategiesCheckbox.addEventListener('change', (e) => {
    if (e.target.checked) {
      singleStrategyGrid.style.display = 'none';
      multiStrategyGrid.style.display = 'block';
    } else {
      singleStrategyGrid.style.display = 'grid';
      multiStrategyGrid.style.display = 'none';
    }
  });
}

/**
 * Knowledge Base Ingestion Flow
 */
function initIngestion() {
  const form = document.getElementById('ingest-form');
  const submitBtn = document.getElementById('ingest-submit-btn');
  const spinner = submitBtn.querySelector('.btn-spinner');
  const btnText = submitBtn.querySelector('span');
  const statusDiv = document.getElementById('ingest-status');
  const statusTitle = document.getElementById('status-title');
  const statusMsg = document.getElementById('status-message');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const title = document.getElementById('ingest-title').value;
    const category = document.getElementById('ingest-category').value;
    const strategy = document.getElementById('ingest-strategy').value;
    const chunkSize = document.getElementById('ingest-chunk-size').value;
    const chunkOverlap = document.getElementById('ingest-chunk-overlap').value;
    const threshold = document.getElementById('ingest-threshold').value;
    const method = document.querySelector('input[name="ingest-method"]:checked').value;
    const ingestAllStrategies = document.getElementById('ingest-all-strategies').checked;

    // Build strategy-specific configuration matrix for multi-ingest
    let configs = {};
    if (ingestAllStrategies) {
      configs = {
        "fixed-size": {
          "chunkSize": parseInt(document.getElementById('multi-fixed-size').value) || 1000,
          "chunkOverlap": parseInt(document.getElementById('multi-fixed-overlap').value) || 200
        },
        "recursive": {
          "chunkSize": parseInt(document.getElementById('multi-recursive-size').value) || 1000,
          "chunkOverlap": parseInt(document.getElementById('multi-recursive-overlap').value) || 200
        },
        "semantic": {
          "chunkSize": parseInt(document.getElementById('multi-semantic-size').value) || 1000,
          "semanticThreshold": document.getElementById('multi-semantic-threshold').value ? parseFloat(document.getElementById('multi-semantic-threshold').value) : null
        },
        "page-based": {
          "chunkSize": parseInt(document.getElementById('multi-page-size').value) || 1500,
          "chunkOverlap": parseInt(document.getElementById('multi-page-overlap').value) || 200
        }
      };
    }

    // Reset status and set loading state
    statusDiv.style.display = 'none';
    statusDiv.className = 'status-alert';
    submitBtn.disabled = true;
    spinner.style.display = 'inline-block';
    btnText.textContent = 'Processing & Indexing Document...';

    try {
      let response;
      let result;

      if (method === 'pdf') {
        const fileInput = document.getElementById('ingest-file');
        if (fileInput.files.length === 0) {
          throw new Error('Please select or drop a PDF file first.');
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('title', title);
        formData.append('category', category);
        formData.append('strategy', strategy);
        formData.append('chunkSize', chunkSize);
        formData.append('chunkOverlap', chunkOverlap);
        formData.append('ingestAllStrategies', ingestAllStrategies);
        if (threshold) {
          formData.append('semanticThreshold', threshold);
        }
        if (ingestAllStrategies) {
          formData.append('configs', JSON.stringify(configs));
        }

        response = await fetch('/api/ingest-pdf', {
          method: 'POST',
          body: formData
        });
      } else {
        const content = document.getElementById('ingest-content').value;
        if (!content.trim()) {
          throw new Error('Please paste document body text first.');
        }

        const payload = {
          content,
          metadata: { title, category },
          strategy,
          chunkSize,
          chunkOverlap,
          semanticThreshold: threshold || undefined,
          ingestAllStrategies,
          configs
        };

        response = await fetch('/api/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Failed to ingest data');
      }

      // Success Display
      statusDiv.classList.add('success');
      statusTitle.textContent = 'Ingestion Successful!';
      
      const sourceLabel = method === 'pdf' ? `PDF (${result.pagesCount} pages)` : 'raw text';
      statusMsg.textContent = `Document "${title}" parsed as ${sourceLabel}. Generated ${result.chunksIngested} chunks using strategy "${strategy}" (Size: ${chunkSize} chars). Embedded and indexed successfully in PostgreSQL!`;
      statusDiv.style.display = 'flex';
      
      // Reset Form fields (except Title/Category so users can batch ingest)
      document.getElementById('ingest-content').value = '';
      document.getElementById('ingest-file').value = '';
      document.getElementById('file-name-display').textContent = 'No file selected';
      document.getElementById('file-drop-zone').classList.remove('has-file');

    } catch (err) {
      console.error(err);
      statusDiv.classList.add('error');
      statusTitle.textContent = 'Ingestion Failed';
      statusMsg.textContent = err.message || 'An error occurred during vector indexing.';
      statusDiv.style.display = 'flex';
    } finally {
      submitBtn.disabled = false;
      spinner.style.display = 'none';
      btnText.textContent = 'Ingest Document & Create Index';
    }
  });
}

/**
 * Hybrid Search Sandbox Flow
 */
function initSearchSandbox() {
  const form = document.getElementById('search-form');
  const resultsList = document.getElementById('search-results');
  const countSpan = document.getElementById('results-count');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('search-input').value;
    const strategy = document.getElementById('search-strategy-select').value;

    resultsList.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-spinner fa-spin"></i>
        <p>Running Reciprocal Rank Fusion on PostgreSQL vector and keyword indexes...</p>
      </div>
    `;

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, strategy })
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Search failed');
      }

      const results = result.results || [];
      countSpan.textContent = `${results.length} chunks retrieved`;

      if (results.length === 0) {
        resultsList.innerHTML = `
          <div class="empty-state">
            <i class="fa-solid fa-triangle-exclamation"></i>
            <p>No results found. Try ingesting some documents first or modify your query.</p>
          </div>
        `;
        return;
      }

      resultsList.innerHTML = '';
      results.forEach(row => {
        const metadata = row.metadata || {};
        const card = document.createElement('div');
        card.className = 'result-card';

        // Format RRF score to 5 decimal places
        const formattedScore = row.rrfScore.toFixed(5);
        const formattedSim = row.similarity ? `${(row.similarity * 100).toFixed(1)}%` : 'N/A';
        
        // Format rank badges
        const semRankText = row.semanticRank ? `#${row.semanticRank}` : 'N/A';
        const keyRankText = row.keywordRank ? `#${row.keywordRank}` : 'N/A';

        const stratDisplay = metadata.strategy 
          ? metadata.strategy.charAt(0).toUpperCase() + metadata.strategy.slice(1)
          : 'Unknown';

        card.innerHTML = `
          <div class="result-card-header">
            <div class="result-meta-left">
              <span class="doc-badge">${metadata.category || 'Documentation'}</span>
              <span class="strat-tag">${stratDisplay}</span>
              <span class="doc-title-text">${metadata.title || 'Untitled Document'}</span>
              ${metadata.page ? `<span class="page-tag"><i class="fa-solid fa-file-lines"></i> Page ${metadata.page}</span>` : ''}
            </div>
            <div class="rrf-score-indicator">
              <div class="ranks-grid">
                <span class="rank-pill semantic">
                  <i class="fa-solid fa-brain"></i> Similarity: <strong>${formattedSim}</strong> (${semRankText})
                </span>
                <span class="rank-pill keyword">
                  <i class="fa-solid fa-keyboard"></i> Keyword: <strong>${keyRankText}</strong>
                </span>
              </div>
              <div class="score-badge">
                <span class="score-num">${formattedScore}</span>
                <span class="score-label">RRF Score</span>
              </div>
            </div>
          </div>
          <div class="result-card-body">${escapeHTML(row.content)}</div>
        `;

        resultsList.appendChild(card);
      });

    } catch (err) {
      console.error(err);
      resultsList.innerHTML = `
        <div class="empty-state" style="color: var(--error-color); border-color: rgba(239, 68, 68, 0.2);">
          <i class="fa-solid fa-circle-exclamation"></i>
          <p>Search failed: ${err.message || 'An error occurred during query execution.'}</p>
        </div>
      `;
    }
  });
}

/**
 * Streaming Customer Support Chat
 */
function initChat() {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const clearBtn = document.getElementById('clear-chat');
  const submitBtn = document.getElementById('chat-submit-btn');
  const strategySelect = document.getElementById('chat-strategy-select');

  // Clear Chat History
  clearBtn.addEventListener('click', () => {
    chatMessages.innerHTML = `
      <div class="message model">
        <div class="message-avatar">
          <i class="fa-solid fa-robot"></i>
        </div>
        <div class="message-bubble">
          <p>Hello! I am your <strong>NexusRAG</strong> Customer Support Bot. Ingest documentation, and ask me anything. I will answer based strictly on the retrieved knowledge base.</p>
        </div>
      </div>
    `;
    chatHistory = [];
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const question = input.value.trim();
    if (!question) return;

    const strategy = strategySelect.value;

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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history: chatHistory, strategy })
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
        
        // Keep the last split part as it might be incomplete
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
                // Render as markdown on the fly
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

      // Save to chat state
      chatHistory.push({ role: 'user', content: question });
      chatHistory.push({ role: 'model', content: accumulatedResponse });

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

/**
 * Strategy Comparison Analysis Dashboard
 */
function initCompareDashboard() {
  const form = document.getElementById('compare-form');
  const grid = document.getElementById('comparison-grid');
  const emptyState = document.getElementById('compare-empty-state');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('compare-input').value;

    emptyState.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-circle-notch fa-spin"></i>
        <p>Running comparative RAG search pipeline across all 4 chunking strategies concurrently...</p>
      </div>
    `;
    emptyState.style.display = 'flex';
    grid.style.display = 'none';

    try {
      const response = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Comparison query failed');
      }

      emptyState.style.display = 'none';
      grid.style.display = 'grid';

      const comparisons = result.comparisons || [];

      // Render each strategy column
      comparisons.forEach(comp => {
        const colContainer = document.getElementById(`compare-res-${comp.strategy}`);
        if (!colContainer) return;

        colContainer.innerHTML = '';

        if (comp.results.length === 0) {
          colContainer.innerHTML = `
            <div class="no-col-results">
              <i class="fa-solid fa-triangle-exclamation"></i>
              <p>No indexed chunks found matching this query for this strategy.</p>
            </div>
          `;
          return;
        }

        comp.results.forEach((chunk, index) => {
          const card = document.createElement('div');
          card.className = 'compare-chunk-card';

          const metadata = chunk.metadata || {};
          const simPct = chunk.similarity ? `${(chunk.similarity * 100).toFixed(1)}%` : 'N/A';
          const rrfScoreStr = chunk.rrfScore.toFixed(5);
          
          card.innerHTML = `
            <div class="compare-chunk-meta">
              <div class="meta-row">
                <span class="chunk-index-badge">Match #${index + 1}</span>
                <span class="chunk-char-count"><i class="fa-solid fa-text-width"></i> ${metadata.charCount || chunk.content.length} chars</span>
              </div>
              <div class="meta-row">
                <span class="chunk-score-stat semantic">
                  <i class="fa-solid fa-brain"></i> Sim: <strong>${simPct}</strong>
                </span>
                <span class="chunk-score-stat keyword">
                  <i class="fa-solid fa-hashtag"></i> RRF: <strong>${rrfScoreStr}</strong>
                </span>
              </div>
              ${metadata.page ? `
              <div class="meta-row font-secondary">
                <span><i class="fa-solid fa-file-pdf"></i> Page ${metadata.page}</span>
              </div>
              ` : ''}
              <div class="meta-row font-secondary truncated-title">
                <span>Source: ${metadata.title || 'Untitled'}</span>
              </div>
            </div>
            <div class="compare-chunk-content" title="Click to view full chunk content" onclick="toggleFullContent(this)">
              ${escapeHTML(chunk.content)}
            </div>
          `;
          colContainer.appendChild(card);
        });
      });

    } catch (err) {
      console.error(err);
      emptyState.innerHTML = `
        <div class="empty-state" style="color: var(--error-color);">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <p>Analysis failed: ${err.message || 'An error occurred during query comparison.'}</p>
        </div>
      `;
      emptyState.style.display = 'flex';
      grid.style.display = 'none';
    }
  });
}

/**
 * Toggle Full Content Display on Click
 */
window.toggleFullContent = function(element) {
  element.classList.toggle('expanded');
};

/**
 * UI Render Helpers
 */
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
  avatar.innerHTML = role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

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
  avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';

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

function escapeHTML(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderMarkdown(text) {
  if (typeof marked !== 'undefined') {
    if (typeof marked.parse === 'function') {
      return marked.parse(text);
    } else if (typeof marked === 'function') {
      return marked(text);
    }
  }
  // Fallback to escaping HTML and replacing newlines with <br>
  return escapeHTML(text).replace(/\n/g, '<br>');
}

function formatBytes(bytes, decimals = 1) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}
