// Application State Variables
let chatHistory = [];
let token = localStorage.getItem('token');
let currentThreadId = null;
let userThreads = [];
let libraryDocs = [];
let attachedDocs = [];

/**
 * Common Helper Utilities
 */
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

// Toggle Full Content Display on Click
window.toggleFullContent = function(element) {
  element.classList.toggle('expanded');
}
