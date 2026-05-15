// @ts-nocheck
// Authentication Management
const DEFAULT_AUTH_IDLE_TIMEOUT_MS = 20 * 60 * 1000;
const DEFAULT_AUTH_HEARTBEAT_MS = 5 * 60 * 1000;
const AUTH_LAST_ACTIVITY_KEY = 'auth_last_activity_at';
const AUTH_LAST_HEARTBEAT_KEY = 'auth_last_heartbeat_at';

class AuthManager {
    constructor() {
        this.token = localStorage.getItem('access_token');
        this.user = null;
        this.idleTimeoutMs = DEFAULT_AUTH_IDLE_TIMEOUT_MS;
        this.heartbeatMs = DEFAULT_AUTH_HEARTBEAT_MS;
        this.idleTimer = null;
        this.activityListenersRegistered = false;
        this.registerActivityListeners();
        this.startIdleWatcher();
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

    ensureActivityTimestamp() {
        if (!localStorage.getItem(AUTH_LAST_ACTIVITY_KEY)) {
            localStorage.setItem(AUTH_LAST_ACTIVITY_KEY, String(Date.now()));
        }
    }

    markActivity(options = {}) {
        if (!this.token && !localStorage.getItem('access_token')) return;
        localStorage.setItem(AUTH_LAST_ACTIVITY_KEY, String(Date.now()));
        if (options.ping === false) return;
        this.maybeSendHeartbeat();
    }

    isIdleExpired() {
        const token = this.token || localStorage.getItem('access_token');
        if (!token) return false;
        if (!Number.isFinite(this.idleTimeoutMs) || this.idleTimeoutMs <= 0) return false;
        const lastActivity = Number(localStorage.getItem(AUTH_LAST_ACTIVITY_KEY) || 0);
        if (!Number.isFinite(lastActivity) || lastActivity <= 0) return false;
        return Date.now() - lastActivity > this.idleTimeoutMs;
    }

    idleTimeoutMinutesLabel() {
        const minutes = Math.max(1, Math.round(Number(this.idleTimeoutMs || DEFAULT_AUTH_IDLE_TIMEOUT_MS) / 60000));
        return String(minutes);
    }

    idleTimeoutMessage() {
        return `به دلیل ${this.idleTimeoutMinutesLabel()} دقیقه بی‌کاری از سامانه خارج شدید.`;
    }

    applySessionMetadata(payload = {}) {
        const idleMinutes = Number(payload?.idle_timeout_minutes);
        if (Number.isFinite(idleMinutes) && idleMinutes >= 0) {
            this.idleTimeoutMs = idleMinutes > 0 ? idleMinutes * 60 * 1000 : 0;
        }
        const heartbeatSeconds = Number(payload?.heartbeat_interval_seconds);
        if (Number.isFinite(heartbeatSeconds) && heartbeatSeconds >= 0) {
            this.heartbeatMs = heartbeatSeconds > 0 ? heartbeatSeconds * 1000 : 0;
        } else if (this.idleTimeoutMs > 0) {
            this.heartbeatMs = Math.max(60000, Math.min(300000, Math.round(this.idleTimeoutMs / 2)));
        }
    }

    registerActivityListeners() {
        if (this.activityListenersRegistered) return;
        this.activityListenersRegistered = true;
        let lastMarkedAt = 0;
        const mark = () => {
            const now = Date.now();
            if (now - lastMarkedAt < 15000) return;
            lastMarkedAt = now;
            this.markActivity();
        };
        ['click', 'keydown', 'mousemove', 'scroll', 'touchstart'].forEach((eventName) => {
            window.addEventListener(eventName, mark, { passive: true });
        });
    }

    startIdleWatcher() {
        if (this.idleTimer) window.clearInterval(this.idleTimer);
        this.idleTimer = window.setInterval(() => {
            if (this.isIdleExpired()) {
                if (window.UI && typeof window.UI.warning === 'function') {
                    window.UI.warning(this.idleTimeoutMessage());
                }
                this.logout({ notifyServer: true });
            }
        }, 60000);
    }

    async maybeSendHeartbeat(force = false) {
        const token = this.token || localStorage.getItem('access_token');
        if (!token) return;
        if (this.isIdleExpired()) {
            this.logout({ notifyServer: true });
            return;
        }
        const now = Date.now();
        const lastHeartbeat = Number(localStorage.getItem(AUTH_LAST_HEARTBEAT_KEY) || 0);
        if (!force && (!Number.isFinite(this.heartbeatMs) || this.heartbeatMs <= 0)) return;
        if (!force && Number.isFinite(lastHeartbeat) && now - lastHeartbeat < this.heartbeatMs) return;
        localStorage.setItem(AUTH_LAST_HEARTBEAT_KEY, String(now));
        try {
            const response = await fetch('/api/v1/auth/me', {
                headers: { 'Authorization': `Bearer ${token}`, 'X-User-Activity': '1' },
                cache: 'no-store',
            });
            if (response.ok) {
                const body = await response.clone().json().catch(() => null);
                if (body) this.applySessionMetadata(body);
            }
            if (response.status === 401) {
                this.logout({ notifyServer: false });
            }
        } catch (error) {
            console.warn('Auth heartbeat failed:', error);
        }
    }

    async validateToken() {
        this.ensureActivityTimestamp();
        if (this.isIdleExpired()) {
            this.logout({ notifyServer: true });
            return;
        }
        try {
            const response = await fetch('/api/v1/auth/me', {
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'X-User-Activity': '1',
                }
            });

            if (response.ok) {
                localStorage.setItem(AUTH_LAST_HEARTBEAT_KEY, String(Date.now()));
                const userData = await response.json();
                this.applySessionMetadata(userData);
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
            const effectiveRole = this.user.effective_role || this.user.role;
            userRoleElement.textContent = this.getRoleLabel(effectiveRole);
        }
    }

    getRoleLabel(role) {
        const key = String(role || '').toLowerCase();
        if (key === 'admin') return 'مدیر سیستم';
        if (key === 'manager') return 'سرپرست';
        if (key === 'dcc') return 'کنترل مدارک';
        if (key === 'project_control') return 'کنترل پروژه';
        if (key === 'viewer') return 'مشاهده‌گر';
        return 'کاربر';
    }

    showAdminMenuIfAdmin() {
        const adminOnlyItems = document.querySelectorAll('.admin-only');
        if (!adminOnlyItems.length) return;

        const isAdmin = Boolean(this.user && this.user.is_system_admin === true);
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
                localStorage.setItem(AUTH_LAST_ACTIVITY_KEY, String(Date.now()));
                localStorage.setItem(AUTH_LAST_HEARTBEAT_KEY, '0');
                
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

    logout(options = {}) {
        const token = this.token || localStorage.getItem('access_token');
        if (options.notifyServer !== false && token) {
            fetch('/api/v1/auth/logout', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
            }).catch(() => undefined);
        }
        // Ã˜Â­Ã˜Â°Ã™Â Ã˜ÂªÃ™Ë†ÃšÂ©Ã™â€  Ã˜Â§Ã˜Â² localStorage
        localStorage.removeItem('access_token');
        localStorage.removeItem(AUTH_LAST_ACTIVITY_KEY);
        localStorage.removeItem(AUTH_LAST_HEARTBEAT_KEY);
        
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
        return Boolean(this.user && this.user.is_system_admin === true);
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
    if (window.authManager && typeof window.authManager.isIdleExpired === 'function' && window.authManager.isIdleExpired()) {
        if (window.UI && typeof window.UI.warning === 'function') {
            window.UI.warning(
                typeof window.authManager.idleTimeoutMessage === 'function'
                    ? window.authManager.idleTimeoutMessage()
                    : 'Session idle timeout'
            );
        }
        window.authManager.logout({ notifyServer: true });
        throw new Error('Session idle timeout');
    }
    const originalOptions = options || {};
    const { authActivity, ...fetchOptions } = originalOptions;
    const headers = originalOptions.headers instanceof Headers
        ? new Headers(originalOptions.headers)
        : new Headers(originalOptions.headers || {});
    const token = localStorage.getItem('access_token');
    let usingJwtToken = false;

    if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
        usingJwtToken = true;
    } else if (token && String(headers.get('Authorization') || '').trim() === `Bearer ${token}`) {
        usingJwtToken = true;
    }

    if (usingJwtToken && authActivity !== false && !headers.has('X-User-Activity')) {
        headers.set('X-User-Activity', '1');
        if (window.authManager && typeof window.authManager.markActivity === 'function') {
            window.authManager.markActivity({ ping: false });
        }
    }

    if (!(originalOptions.body instanceof FormData) && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    const config = { ...fetchOptions, headers };
    const max429Retries = Number.isFinite(originalOptions.max429Retries) ? Number(originalOptions.max429Retries) : 0;
    const base429DelayMs = Number.isFinite(originalOptions.base429DelayMs) ? Number(originalOptions.base429DelayMs) : 700;
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
            if (window.authManager && typeof window.authManager.logout === 'function') {
                window.authManager.logout({ notifyServer: false });
            } else {
                localStorage.removeItem('access_token');
                setTimeout(() => window.location.href = '/login', 2000);
            }
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

