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
    const yearSelect = document.getElementById('search-year-select').value;
    const quarterSelect = document.getElementById('search-quarter-select').value;
    
    const fiscalYear = yearSelect === 'all' ? null : parseInt(yearSelect);
    const quarter = quarterSelect === 'all' ? null : quarterSelect;

    resultsList.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-spinner fa-spin"></i>
        <p>Running Reciprocal Rank Fusion on PostgreSQL vector and keyword indexes...</p>
      </div>
    `;

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ query, strategy, fiscalYear, quarter })
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

        const formattedScore = row.rrfScore.toFixed(5);
        const formattedSim = row.similarity ? `${(row.similarity * 100).toFixed(1)}%` : 'N/A';
        
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
              ${metadata.fiscal_year ? `<span class="year-tag"><i class="fa-solid fa-calendar"></i> ${metadata.fiscal_year}</span>` : ''}
              ${metadata.quarter ? `<span class="quarter-tag"><i class="fa-solid fa-clock"></i> ${metadata.quarter}</span>` : ''}
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
 * Comparative Ingestion Strategy Dashboard
 */
function initCompareDashboard() {
  const form = document.getElementById('compare-form');
  const emptyState = document.getElementById('compare-empty-state');
  const compareGrid = document.getElementById('comparison-grid');
  const strategies = ["fixed-size", "recursive", "semantic", "page-based"];

  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('compare-input').value.trim();
    if (!query) return;

    const yearSelect = document.getElementById('compare-year-select').value;
    const quarterSelect = document.getElementById('compare-quarter-select').value;
    const fiscalYear = yearSelect === 'all' ? null : parseInt(yearSelect);
    const quarter = quarterSelect === 'all' ? null : quarterSelect;

    emptyState.style.display = 'none';
    compareGrid.style.display = 'grid';
    
    strategies.forEach(strat => {
      const container = document.getElementById(`compare-res-${strat}`);
      if (container) {
        container.innerHTML = `
          <div class="compare-loading">
            <i class="fa-solid fa-circle-notch fa-spin"></i>
            <span>Searching...</span>
          </div>
        `;
      }
    });

    try {
      const response = await fetch('/api/compare', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ query, fiscalYear, quarter })
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Comparison analysis failed.');
      }

      const comparisons = result.comparisons || [];

      comparisons.forEach(item => {
        const strat = item.strategy;
        const results = item.results || [];
        const container = document.getElementById(`compare-res-${strat}`);
        if (!container) return;

        if (results.length === 0) {
          container.innerHTML = `
            <div class="compare-empty-column">
              <i class="fa-solid fa-folder-open"></i>
              <p>No matching chunks</p>
            </div>
          `;
          return;
        }

        container.innerHTML = '';
        results.forEach((row, index) => {
          const card = document.createElement('div');
          card.className = 'compare-chunk-card';

          const formattedSim = row.similarity ? `${(row.similarity * 100).toFixed(0)}%` : 'N/A';
          const rrfScoreText = row.rrfScore.toFixed(4);

          card.innerHTML = `
            <div class="compare-chunk-meta">
              <span class="sim"><i class="fa-solid fa-brain"></i> Sim: ${formattedSim}</span>
              <span class="rrf"><i class="fa-solid fa-arrow-down-short-wide"></i> RRF: ${rrfScoreText}</span>
              <span class="chunk-index-badge">Match #${index + 1}</span>
            </div>
            <div class="compare-chunk-content" title="Click to view full chunk content" onclick="toggleFullContent(this)">
              ${escapeHTML(row.content)}
            </div>
          `;

          container.appendChild(card);
        });
      });

    } catch (err) {
      console.error(err);
      strategies.forEach(strat => {
        const container = document.getElementById(`compare-res-${strat}`);
        if (container) {
          container.innerHTML = `
            <div class="compare-error-column">
              <i class="fa-solid fa-circle-xmark"></i>
              <p>Error loading results</p>
            </div>
          `;
        }
      });
    }
  });
}
