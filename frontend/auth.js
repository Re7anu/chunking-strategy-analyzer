/**
 * Authentication UI Controller
 */
function initAuthUI() {
  const overlay = document.getElementById('auth-overlay');
  const form = document.getElementById('auth-form-ui');
  const emailInput = document.getElementById('auth-email');
  const passwordInput = document.getElementById('auth-password');
  const usernameInput = document.getElementById('auth-username');
  const usernameGroup = document.getElementById('username-group-ui');
  const submitBtn = document.getElementById('auth-btn-ui');
  const toggleLink = document.getElementById('auth-toggle-link');
  const togglePrompt = document.getElementById('auth-toggle-prompt');
  const subtitle = document.getElementById('auth-subtitle');
  const errorMsg = document.getElementById('auth-error-msg');
  const logoutBtn = document.getElementById('sidebar-logout-btn');

  let mode = 'login'; // or 'register'

  // If already logged in, validate token
  if (token) {
    validateToken();
  } else {
    if (overlay) overlay.style.display = 'flex';
  }

  if (toggleLink) {
    toggleLink.addEventListener('click', (e) => {
      e.preventDefault();
      errorMsg.style.display = 'none';
      if (mode === 'login') {
        mode = 'register';
        subtitle.textContent = 'Create a new account';
        usernameGroup.style.display = 'block';
        usernameInput.required = true;
        submitBtn.textContent = 'Register';
        togglePrompt.textContent = 'Already have an account?';
        toggleLink.textContent = 'Login here';
      } else {
        mode = 'login';
        subtitle.textContent = 'Login to access your RAG Sandbox';
        usernameGroup.style.display = 'none';
        usernameInput.required = false;
        submitBtn.textContent = 'Login';
        togglePrompt.textContent = "Don't have an account?";
        toggleLink.textContent = 'Register here';
      }
    });
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorMsg.style.display = 'none';
      submitBtn.disabled = true;

      const email = emailInput.value.trim();
      const password = passwordInput.value;
      const username = usernameInput.value.trim();

      if (mode === 'register') {
        const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        if (!emailRegex.test(email)) {
          errorMsg.textContent = 'Please enter a valid email address (e.g. user@domain.com).';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }

        if (password.length < 8) {
          errorMsg.textContent = 'Password must be at least 8 characters long.';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }

        if (!/[A-Z]/.test(password)) {
          errorMsg.textContent = 'Password must contain at least one uppercase letter.';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }

        if (!/[a-z]/.test(password)) {
          errorMsg.textContent = 'Password must contain at least one lowercase letter.';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }

        if (!/[0-9]/.test(password)) {
          errorMsg.textContent = 'Password must contain at least one number.';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }

        if (!/[^a-zA-Z0-9\s]/.test(password)) {
          errorMsg.textContent = 'Password must contain at least one special character (e.g. !@#$%^&*).';
          errorMsg.style.display = 'block';
          submitBtn.disabled = false;
          return;
        }
      }

      try {
        let endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
        let body = mode === 'login' ? { email, password } : { username, email, password };

        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Authentication failed.');
        }

        // Save token and username
        token = data.token;
        localStorage.setItem('token', token);
        localStorage.setItem('username', data.username || 'User');

        // Hide overlay and update sidebar
        if (overlay) overlay.style.display = 'none';
        updateProfilePanel(data.username || 'User');

      } catch (err) {
        errorMsg.textContent = err.message;
        errorMsg.style.display = 'block';
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  const logoutConfirmModal = document.getElementById('logout-confirm-modal');
  const logoutCancelBtn = document.getElementById('logout-cancel-btn');
  const logoutConfirmBtn = document.getElementById('logout-confirm-btn');

  if (logoutBtn && logoutConfirmModal && logoutCancelBtn && logoutConfirmBtn) {
    logoutBtn.addEventListener('click', () => {
      logoutConfirmModal.style.display = 'flex';
    });

    logoutCancelBtn.addEventListener('click', () => {
      logoutConfirmModal.style.display = 'none';
    });

    window.addEventListener('click', (e) => {
      if (e.target === logoutConfirmModal) {
        logoutConfirmModal.style.display = 'none';
      }
    });

    logoutConfirmBtn.addEventListener('click', async () => {
      logoutConfirmModal.style.display = 'none';
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
      } catch (err) {
        console.error('Logout request failed:', err);
      } finally {
        token = null;
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        updateProfilePanel(null);
        if (overlay) {
          overlay.style.display = 'flex';
          emailInput.value = '';
          passwordInput.value = '';
          usernameInput.value = '';
        }
      }
    });
  }
}

async function validateToken() {
  const overlay = document.getElementById('auth-overlay');
  try {
    const res = await fetch('/api/auth/me', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!res.ok) throw new Error('Token invalid');
    const data = await res.json();
    
    if (overlay) overlay.style.display = 'none';
    updateProfilePanel(data.username);
  } catch (err) {
    console.warn('Authentication token expired or invalid:', err);
    token = null;
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    updateProfilePanel(null);
    if (overlay) overlay.style.display = 'flex';
  }
}

function updateProfilePanel(username) {
  const panel = document.getElementById('user-profile-panel');
  const nameSpan = document.getElementById('sidebar-username');
  if (panel && nameSpan) {
    if (username) {
      nameSpan.textContent = username;
      panel.style.display = 'block';
      loadThreads();
      loadLibrary();
    } else {
      panel.style.display = 'none';
      currentThreadId = null;
      document.getElementById('sidebar-threads-list').innerHTML = '';
      document.getElementById('attached-docs-list').innerHTML = '';
    }
  }
}
