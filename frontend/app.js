document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initAuthUI();
  initIngestionMode();
  initIngestion();
  initSearchSandbox();
  initChat();
  initCompareDashboard();
  initPersistenceUI();
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
