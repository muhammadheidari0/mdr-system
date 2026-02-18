// @ts-nocheck
// Authentication Management
class AuthManager {
    constructor() {
        this.token = localStorage.getItem('access_token');
        this.user = null;
        this.init();
    }

    init() {
        // Ã¢â€ºâ€ Ã™â€žÃ›Å’Ã˜Â³Ã˜Âª Ã˜ÂµÃ™ÂÃ˜Â­Ã˜Â§Ã˜Âª Ã˜Â¹Ã™â€¦Ã™Ë†Ã™â€¦Ã›Å’ ÃšÂ©Ã™â€¡ Ã™â€ Ã˜Â¨Ã˜Â§Ã›Å’Ã˜Â¯ Ãšâ€ ÃšÂ© Ã˜Â´Ã™Ë†Ã™â€ Ã˜Â¯
        const publicPages = ['/login', '/debug_login'];
        const path = window.location.pathname;
        
        // Ã˜Â§ÃšÂ¯Ã˜Â± Ã˜Â¯Ã˜Â± Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã˜Â¹Ã™â€¦Ã™Ë†Ã™â€¦Ã›Å’ Ã™â€¡Ã˜Â³Ã˜ÂªÃ›Å’Ã™â€¦Ã˜Å’ Ã™â€¦Ã™â€ Ã˜Â·Ã™â€š Ã˜Â§Ã˜Â­Ã˜Â±Ã˜Â§Ã˜Â² Ã™â€¡Ã™Ë†Ã›Å’Ã˜Âª Ã˜Â±Ã˜Â§ Ã˜Â§Ã˜Â¬Ã˜Â±Ã˜Â§ Ã™â€ ÃšÂ©Ã™â€ 
        if (publicPages.includes(path)) {
            console.log("Skipping auth check on public page:", path);
            if (path === '/login') {
                this.showLoginView();
            }
            return;
        }
        
        // Ã˜Â¨Ã˜Â±Ã˜Â±Ã˜Â³Ã›Å’ Ã˜ÂªÃ™Ë†ÃšÂ©Ã™â€  Ã˜Â¯Ã˜Â± Ã™â€¡Ã™â€ ÃšÂ¯Ã˜Â§Ã™â€¦ Ã˜Â¨Ã˜Â§Ã˜Â±ÃšÂ¯Ã˜Â°Ã˜Â§Ã˜Â±Ã›Å’ Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡
        if (this.token) {
            this.validateToken();
        } else {
            this.redirectToLogin();
        }
    }

    async validateToken() {
        try {
            const response = await fetch('/api/v1/auth/me', {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                const userData = await response.json();
                this.user = userData;
                this.updateUI();
                this.showAdminMenuIfAdmin();
                this.showMainApp(); // Ã™â€ Ã™â€¦Ã˜Â§Ã›Å’Ã˜Â´ Ã˜Â§Ã™Â¾Ã™â€žÃ›Å’ÃšÂ©Ã›Å’Ã˜Â´Ã™â€  Ã˜Â§Ã˜ÂµÃ™â€žÃ›Å’ Ã™Â¾Ã˜Â³ Ã˜Â§Ã˜Â² Ã™Ë†Ã˜Â±Ã™Ë†Ã˜Â¯ Ã™â€¦Ã™Ë†Ã™ÂÃ™â€š
            } else {
                this.logout();
            }
        } catch (error) {
            console.error('Token validation error:', error);
            this.logout();
        }
    }

    updateUI() {
        // Ã˜Â¨Ã™â€¡Ã¢â‚¬Å’Ã˜Â±Ã™Ë†Ã˜Â²Ã˜Â±Ã˜Â³Ã˜Â§Ã™â€ Ã›Å’ Ã˜Â§Ã˜Â·Ã™â€žÃ˜Â§Ã˜Â¹Ã˜Â§Ã˜Âª ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â± Ã˜Â¯Ã˜Â± Ã™â€¡Ã˜Â¯Ã˜Â±
        const userNameElement = document.querySelector('.username');
        const userNameHeader = document.querySelector('.user-info-header .name');
        const userEmailHeader = document.querySelector('.user-info-header .email');
        const avatarElement = document.querySelector('.avatar');
        
        if (this.user && userNameElement) {
            userNameElement.textContent = this.user.full_name || this.user.email;
        }
        
        if (this.user && userNameHeader) {
            userNameHeader.textContent = this.user.full_name || this.user.email;
        }

        if (this.user && userEmailHeader) {
            userEmailHeader.textContent = this.user.email || '-';
        }

        if (this.user && avatarElement) {
            const base = (this.user.full_name || this.user.email || 'US').trim();
            const parts = base.split(/\s+/).filter(Boolean);
            const initials = (parts[0]?.[0] || '') + (parts[1]?.[0] || '');
            avatarElement.textContent = (initials || base.slice(0, 2) || 'US').toUpperCase();
        }

        // Ã˜Â¨Ã™â€¡Ã¢â‚¬Å’Ã˜Â±Ã™Ë†Ã˜Â²Ã˜Â±Ã˜Â³Ã˜Â§Ã™â€ Ã›Å’ Ã™â€ Ã™â€šÃ˜Â´ ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â±
        const userRoleElement = document.querySelector('.user-info-header .role');
        if (this.user && userRoleElement) {
            userRoleElement.textContent = this.getRoleLabel(this.user.role);
        }
    }

    getRoleLabel(role) {
        const key = String(role || '').toLowerCase();
        if (key === 'admin') return 'Ã™â€¦Ã˜Â¯Ã›Å’Ã˜Â± Ã˜Â§Ã˜Â±Ã˜Â´Ã˜Â¯';
        if (key === 'manager') return 'Ã˜Â³Ã˜Â±Ã™Â¾Ã˜Â±Ã˜Â³Ã˜Âª';
        if (key === 'viewer') return 'Ã™â€¦Ã˜Â´Ã˜Â§Ã™â€¡Ã˜Â¯Ã™â€¡Ã¢â‚¬Å’ÃšÂ¯Ã˜Â±';
        return 'ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â±';
    }

    showAdminMenuIfAdmin() {
        const adminOnlyItems = document.querySelectorAll('.admin-only');
        if (!adminOnlyItems.length) return;

        const isAdmin = this.user && String(this.user.role || '').toLowerCase() === 'admin';
        adminOnlyItems.forEach((el) => {
            el.style.display = isAdmin ? '' : 'none';
        });
    }

    async login(email, password) {
        try {
            // Ã¢Å“â€¦ Ã˜Â±Ã™Ë†Ã˜Â´ Ã˜ÂµÃ˜Â­Ã›Å’Ã˜Â­ Ã˜Â§Ã˜Â±Ã˜Â³Ã˜Â§Ã™â€ž Ã˜Â¯Ã˜Â§Ã˜Â¯Ã™â€¡ Ã˜Â¨Ã˜Â±Ã˜Â§Ã›Å’ OAuth2 Ã˜Â¯Ã˜Â± FastAPI
            const formData = new URLSearchParams();
            formData.append('username', email); // Ã˜Â­Ã˜ÂªÃ›Å’ Ã˜Â§ÃšÂ¯Ã˜Â± Ã˜Â§Ã›Å’Ã™â€¦Ã›Å’Ã™â€ž Ã˜Â§Ã˜Â³Ã˜ÂªÃ˜Å’ Ã™â€ Ã˜Â§Ã™â€¦ Ã™ÂÃ›Å’Ã™â€žÃ˜Â¯ Ã˜Â¨Ã˜Â§Ã›Å’Ã˜Â¯ username Ã˜Â¨Ã˜Â§Ã˜Â´Ã˜Â¯
            formData.append('password', password);

            const response = await fetch('/api/v1/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData // Ã˜Â§Ã˜Â±Ã˜Â³Ã˜Â§Ã™â€ž Ã˜Â¨Ã™â€¡ Ã˜ÂµÃ™Ë†Ã˜Â±Ã˜Âª Ã™ÂÃ˜Â±Ã™â€¦Ã˜Å’ Ã™â€ Ã™â€¡ JSON
            });

            const data = await response.json();

            if (response.ok) {
                this.token = data.access_token;
                localStorage.setItem('access_token', this.token);
                
                // Ã˜Â¯Ã˜Â±Ã›Å’Ã˜Â§Ã™ÂÃ˜Âª Ã˜Â§Ã˜Â·Ã™â€žÃ˜Â§Ã˜Â¹Ã˜Â§Ã˜Âª ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â±
                await this.validateToken();
                
                return { success: true };
            } else {
                return { success: false, error: data.detail || 'خطا در ورود' };
            }
        } catch (error) {
            console.error('Login error:', error);
            return { success: false, error: 'خطا در ارتباط با سرور' };
        }
    }

    logout() {
        // Ã˜Â­Ã˜Â°Ã™Â Ã˜ÂªÃ™Ë†ÃšÂ©Ã™â€  Ã˜Â§Ã˜Â² localStorage
        localStorage.removeItem('access_token');
        
        // Ã™Â¾Ã˜Â§ÃšÂ© ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜Â§Ã˜Â·Ã™â€žÃ˜Â§Ã˜Â¹Ã˜Â§Ã˜Âª ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â±
        this.token = null;
        this.user = null;
        
        // Ã˜Â§Ã™â€ Ã˜ÂªÃ™â€šÃ˜Â§Ã™â€ž Ã˜Â¨Ã™â€¡ Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã™â€žÃ˜Â§ÃšÂ¯Ã›Å’Ã™â€ 
        this.redirectToLogin();
    }

    redirectToLogin() {
        // Ã˜Â§ÃšÂ¯Ã˜Â± Ã˜Â¯Ã˜Â± Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã™â€žÃ˜Â§ÃšÂ¯Ã›Å’Ã™â€  Ã™â€ Ã›Å’Ã˜Â³Ã˜ÂªÃ›Å’Ã™â€¦Ã˜Å’ Ã˜Â¨Ã™â€¡ Ã˜Â¢Ã™â€  Ã™â€¦Ã™â€ Ã˜ÂªÃ™â€šÃ™â€ž Ã˜Â´Ã™Ë†Ã›Å’Ã™â€¦
        if (!window.location.pathname.includes('/login')) {
            window.location.href = '/login';
        }
    }

    isAuthenticated() {
        return !!this.token && !!this.user;
    }

    isAdmin() {
        return this.user && String(this.user.role || '').toLowerCase() === 'admin';
    }

    getToken() {
        return this.token;
    }

    showLoginView() {
        // Ã™â€¦Ã˜Â®Ã™ÂÃ›Å’ ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜ÂªÃ™â€¦Ã˜Â§Ã™â€¦ Ã™Ë†Ã›Å’Ã™Ë†Ã™â€¡Ã˜Â§
        document.querySelectorAll('.view').forEach(view => {
            view.style.display = 'none';
        });
        
        // Ã™â€ Ã™â€¦Ã˜Â§Ã›Å’Ã˜Â´ Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã™â€žÃ˜Â§ÃšÂ¯Ã›Å’Ã™â€ 
        const loginView = document.getElementById('view-login');
        if (loginView) {
            loginView.style.display = 'block';
        }
        
        // Ã™â€¦Ã˜Â®Ã™ÂÃ›Å’ ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜Â³Ã˜Â§Ã›Å’Ã˜Â¯Ã˜Â¨Ã˜Â§Ã˜Â± Ã™Ë† Ã™â€¡Ã˜Â¯Ã˜Â±
        const sidebar = document.getElementById('app-sidebar');
        const header = document.querySelector('.app-header');
        if (sidebar) sidebar.style.display = 'none';
        if (header) header.style.display = 'none';
        
        // Ã˜ÂªÃ˜ÂºÃ›Å’Ã›Å’Ã˜Â± Ã˜Â§Ã˜Â³Ã˜ÂªÃ˜Â§Ã›Å’Ã™â€ž Ã˜Â¨Ã˜Â¯Ã™â€ Ã™â€¡ Ã˜Â¨Ã˜Â±Ã˜Â§Ã›Å’ Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã™â€žÃ˜Â§ÃšÂ¯Ã›Å’Ã™â€ 
        document.body.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
    }

    showMainApp() {
        // Ã™â€ Ã™â€¦Ã˜Â§Ã›Å’Ã˜Â´ Ã˜Â³Ã˜Â§Ã›Å’Ã˜Â¯Ã˜Â¨Ã˜Â§Ã˜Â± Ã™Ë† Ã™â€¡Ã˜Â¯Ã˜Â±
        const sidebar = document.getElementById('app-sidebar');
        const header = document.querySelector('.app-header');
        if (sidebar) sidebar.style.display = 'flex';
        if (header) header.style.display = 'flex';
        
        // Ã˜Â¨Ã˜Â§Ã˜Â²ÃšÂ¯Ã˜Â±Ã˜Â¯Ã˜Â§Ã™â€ Ã˜Â¯Ã™â€  Ã˜Â§Ã˜Â³Ã˜ÂªÃ˜Â§Ã›Å’Ã™â€ž Ã˜Â¨Ã˜Â¯Ã™â€ Ã™â€¡
        document.body.style.background = '';
        
        // Ã™â€¦Ã˜Â®Ã™ÂÃ›Å’ ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜ÂµÃ™ÂÃ˜Â­Ã™â€¡ Ã™â€žÃ˜Â§ÃšÂ¯Ã›Å’Ã™â€ 
        const loginView = document.getElementById('view-login');
        if (loginView) {
            loginView.style.display = 'none';
        }
        
        // Main app navigation is handled by the boot sequence in app.ts.
    }
}

// Ã˜Â§Ã›Å’Ã˜Â¬Ã˜Â§Ã˜Â¯ Ã™â€ Ã™â€¦Ã™Ë†Ã™â€ Ã™â€¡ Ã˜Â³Ã˜Â±Ã˜Â§Ã˜Â³Ã˜Â±Ã›Å’ Ã˜Â§Ã˜Â² Ã™â€¦Ã˜Â¯Ã›Å’Ã˜Â±Ã›Å’Ã˜Âª Ã˜Â§Ã˜Â­Ã˜Â±Ã˜Â§Ã˜Â² Ã™â€¡Ã™Ë†Ã›Å’Ã˜Âª
window.authManager = new AuthManager();

// Ã˜ÂªÃ™Ë†Ã˜Â§Ã˜Â¨Ã˜Â¹ ÃšÂ©Ã™â€¦ÃšÂ©Ã›Å’ Ã˜Â¨Ã˜Â±Ã˜Â§Ã›Å’ Ã˜Â§Ã˜Â³Ã˜ÂªÃ™ÂÃ˜Â§Ã˜Â¯Ã™â€¡ Ã˜Â¯Ã˜Â± Ã˜Â³Ã˜Â§Ã›Å’Ã˜Â± Ã˜Â¨Ã˜Â®Ã˜Â´Ã¢â‚¬Å’Ã™â€¡Ã˜Â§
window.requireAuth = function() {
    if (!window.authManager?.getToken?.()) {
        window.authManager.redirectToLogin();
        return false;
    }
    return true;
};

window.requireAdmin = function() {
    if (!window.authManager.isAdmin()) {
        showToast('Ã˜Â´Ã™â€¦Ã˜Â§ Ã˜Â¯Ã˜Â³Ã˜ÂªÃ˜Â±Ã˜Â³Ã›Å’ Ã™â€žÃ˜Â§Ã˜Â²Ã™â€¦ Ã˜Â¨Ã˜Â±Ã˜Â§Ã›Å’ Ã˜Â§Ã›Å’Ã™â€  Ã˜Â¹Ã™â€¦Ã™â€žÃ›Å’Ã˜Â§Ã˜Âª Ã˜Â±Ã˜Â§ Ã™â€ Ã˜Â¯Ã˜Â§Ã˜Â±Ã›Å’Ã˜Â¯', 'error');
        return false;
    }
    return true;
};

// Ã˜Â§Ã˜Â¶Ã˜Â§Ã™ÂÃ™â€¡ ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜Â¯ÃšÂ©Ã™â€¦Ã™â€¡ Ã˜Â®Ã˜Â±Ã™Ë†Ã˜Â¬ Ã˜Â¨Ã™â€¡ Ã™â€¦Ã™â€ Ã™Ë†Ã›Å’ ÃšÂ©Ã˜Â§Ã˜Â±Ã˜Â¨Ã˜Â±
document.addEventListener('DOMContentLoaded', function() {
    // Ã˜Â§Ã›Å’Ã˜Â¬Ã˜Â§Ã˜Â¯ Ã˜Â¯ÃšÂ©Ã™â€¦Ã™â€¡ Ã˜Â®Ã˜Â±Ã™Ë†Ã˜Â¬ Ã˜Â§ÃšÂ¯Ã˜Â± Ã™Ë†Ã˜Â¬Ã™Ë†Ã˜Â¯ Ã™â€ Ã˜Â¯Ã˜Â§Ã˜Â±Ã˜Â¯
    const userDropdown = document.getElementById('user-dropdown');
    if (userDropdown) {
        // Ã˜Â¨Ã˜Â±Ã˜Â±Ã˜Â³Ã›Å’ Ã™Ë†Ã˜Â¬Ã™Ë†Ã˜Â¯ Ã˜Â¯ÃšÂ©Ã™â€¦Ã™â€¡ Ã˜Â®Ã˜Â±Ã™Ë†Ã˜Â¬
        const logoutBtn = userDropdown.querySelector('.dropdown-item.text-danger');
        if (!logoutBtn) {
            // Ã˜Â§Ã›Å’Ã˜Â¬Ã˜Â§Ã˜Â¯ Ã˜Â¯ÃšÂ©Ã™â€¦Ã™â€¡ Ã˜Â®Ã˜Â±Ã™Ë†Ã˜Â¬
            const logoutItem = document.createElement('a');
            logoutItem.href = '#';
            logoutItem.className = 'dropdown-item text-danger';
            logoutItem.innerHTML = '<span class="material-icons-round">logout</span> Ã˜Â®Ã˜Â±Ã™Ë†Ã˜Â¬';
            logoutItem.onclick = function(e) {
                e.preventDefault();
                window.authManager.logout();
            };
            
            // Ã˜Â§Ã˜Â¶Ã˜Â§Ã™ÂÃ™â€¡ ÃšÂ©Ã˜Â±Ã˜Â¯Ã™â€  Ã˜Â¨Ã™â€¡ Ã™â€¦Ã™â€ Ã™Ë†Ã›Å’ ÃšÂ©Ã˜Â´Ã™Ë†Ã›Å’Ã›Å’
            userDropdown.appendChild(logoutItem);
        }
    }
});

// Central authenticated request helper
async function fetchWithAuth(url, options = {}) {
    const headers = options.headers || {};
    const token = localStorage.getItem('access_token');

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    const config = { ...options, headers };
    const max429Retries = Number.isFinite(options.max429Retries) ? Number(options.max429Retries) : 0;
    const base429DelayMs = Number.isFinite(options.base429DelayMs) ? Number(options.base429DelayMs) : 700;
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    function parseRetryAfterMs(response, fallbackMs) {
        const header = response && response.headers ? response.headers.get('Retry-After') : null;
        if (!header) return fallbackMs;
        const numeric = Number(header);
        if (Number.isFinite(numeric) && numeric >= 0) {
            return Math.max(200, Math.round(numeric * 1000));
        }
        const dateMs = Date.parse(header);
        if (!Number.isNaN(dateMs)) {
            return Math.max(200, dateMs - Date.now());
        }
        return fallbackMs;
    }

    try {
        let response = null;
        let attempt = 0;

        while (true) {
            response = await fetch(url, config);
            if (response.status !== 429 || attempt >= max429Retries) break;
            const fallbackDelay = base429DelayMs * Math.pow(2, attempt);
            const waitMs = parseRetryAfterMs(response, fallbackDelay);
            await sleep(waitMs);
            attempt += 1;
        }

        if (response.status === 401) {
            UI.error('Your session has expired. Please login again.');
            setTimeout(() => window.location.href = '/login', 2000);
            throw new Error('Unauthorized');
        }

        if (response.status === 403) {
            UI.error('You do not have permission for this action.');
            throw new Error('Forbidden');
        }

        if (response.status === 429) {
            const message = 'Too many requests. Please wait a few seconds.';
            if (window.UI && typeof window.UI.warning === 'function') {
                window.UI.warning(message);
            } else if (typeof showToast === 'function') {
                showToast(message, 'warning');
            }
        }

        if (response.status >= 500) {
            try {
                const errData = await response.clone().json();
                UI.error(`Server error: ${errData.detail || 'Unknown issue'}`);
            } catch (e) {
                UI.error('Internal server error occurred.');
            }
        }

        return response;
    } catch (error) {
        if (error.message !== 'Unauthorized' && error.message !== 'Forbidden') {
            console.error('Network Error:', error);
            UI.error('Network error! Please check your connection.');
        }
        throw error;
    }
}

function getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        throw new Error("No token found");
    }
    return {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };
}

// Preserve legacy global contracts for modules that now run in ES module scope.
window.fetchWithAuth = fetchWithAuth;
window.getAuthHeaders = getAuthHeaders;

