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

    // Toggle overlap field
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
    const fiscalYear = document.getElementById('ingest-year').value;
    const quarter = document.getElementById('ingest-quarter').value;

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
        if (fiscalYear) {
          formData.append('fiscalYear', fiscalYear);
        }
        if (quarter) {
          formData.append('quarter', quarter);
        }
        if (currentThreadId) {
          formData.append('threadId', currentThreadId);
        }
        if (ingestAllStrategies) {
          formData.append('configs', JSON.stringify(configs));
        }

        response = await fetch('/api/ingest-pdf', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
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
          configs,
          fiscalYear: fiscalYear || undefined,
          quarter: quarter || undefined,
          threadId: currentThreadId || undefined
        };

        response = await fetch('/api/ingest', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(payload)
        });
      }

      result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Failed to ingest data');
      }

      statusDiv.classList.add('success');
      statusTitle.textContent = 'Ingestion Successful!';
      
      const sourceLabel = method === 'pdf' ? `PDF (${result.pagesCount} pages)` : 'raw text';
      let detailMsg = `Document "${title}" parsed as ${sourceLabel}. Generated ${result.chunksIngested} chunks using strategy "${strategy}" (Size: ${chunkSize} chars). Embedded and indexed successfully in Qdrant!`;
      if (result.detectedYear || result.detectedQuarter) {
        detailMsg += ` Detected Metadata: Year: ${result.detectedYear || 'N/A'}, Quarter: ${result.detectedQuarter || 'N/A'}.`;
      }
      statusMsg.textContent = detailMsg;
      statusDiv.style.display = 'flex';
      
      loadLibrary();
      
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
 * Fetch and Render Ingested Documents Inventory
 */
async function loadLibrary() {
  const libContainer = document.getElementById('library-items-list');
  if (!libContainer || !token) return;

  try {
    const res = await fetch('/api/documents', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch library docs');
    const data = await res.json();
    libraryDocs = data.documents || [];

    libContainer.innerHTML = '';
    if (libraryDocs.length === 0) {
      libContainer.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 3rem 1rem;">
          <i class="fa-solid fa-box-open" style="font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.4;"></i>
          <p style="font-size: 0.85rem; margin: 0;">No documents ingested yet. Feed text or upload a PDF above to build your RAG index.</p>
        </div>
      `;
      return;
    }

    libraryDocs.forEach(d => {
      const item = document.createElement('div');
      item.className = 'library-item';
      
      const fileIcon = d.filename.endsWith('.pdf') ? 'fa-file-pdf' : 'fa-file-lines';
      const fileColor = d.filename.endsWith('.pdf') ? 'color: #ef4444;' : 'color: var(--accent-cyan);';

      item.innerHTML = `
        <div class="library-item-info">
          <div class="library-item-title" title="${escapeHTML(d.filename)}">
            <i class="fa-solid ${fileIcon}" style="${fileColor} margin-right: 0.35rem;"></i>
            <strong>${escapeHTML(d.filename)}</strong>
          </div>
          <div class="library-item-stats">
            <span>Pages: ${d.pagesCount}</span>
            <span>Chunks: ${d.chunksCount}</span>
            <span>Added: ${new Date(d.createdAt).toLocaleDateString()}</span>
          </div>
        </div>
      `;
      libContainer.appendChild(item);
    });
  } catch (err) {
    console.error('Error loading library inventory:', err);
  }
}
