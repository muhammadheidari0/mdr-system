// Authentication Management
class AuthManager {
    constructor() {
        this.token = localStorage.getItem('access_token');
        this.user = null;
        this.init();
    }

    init() {
        // ⛔ لیست صفحات عمومی که نباید چک شوند
        const publicPages = ['/login', '/debug_login'];
        const path = window.location.pathname;
        
        // اگر در صفحه عمومی هستیم، منطق احراز هویت را اجرا نکن
        if (publicPages.includes(path)) {
            console.log("Skipping auth check on public page:", path);
            this.showLoginView();
            return;
        }
        
        // بررسی توکن در هنگام بارگذاری صفحه
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
                this.showMainApp(); // نمایش اپلیکیشن اصلی پس از ورود موفق
            } else {
                this.logout();
            }
        } catch (error) {
            console.error('Token validation error:', error);
            this.logout();
        }
    }

    updateUI() {
        // به‌روزرسانی اطلاعات کاربر در هدر
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

        // به‌روزرسانی نقش کاربر
        const userRoleElement = document.querySelector('.user-info-header .role');
        if (this.user && userRoleElement) {
            userRoleElement.textContent = this.getRoleLabel(this.user.role);
        }
    }

    getRoleLabel(role) {
        const key = String(role || '').toLowerCase();
        if (key === 'admin') return 'مدیر ارشد';
        if (key === 'manager') return 'سرپرست';
        if (key === 'viewer') return 'مشاهده‌گر';
        return 'کاربر';
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
            // ✅ روش صحیح ارسال داده برای OAuth2 در FastAPI
            const formData = new URLSearchParams();
            formData.append('username', email); // حتی اگر ایمیل است، نام فیلد باید username باشد
            formData.append('password', password);

            const response = await fetch('/api/v1/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData // ارسال به صورت فرم، نه JSON
            });

            const data = await response.json();

            if (response.ok) {
                this.token = data.access_token;
                localStorage.setItem('access_token', this.token);
                
                // دریافت اطلاعات کاربر
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
        // حذف توکن از localStorage
        localStorage.removeItem('access_token');
        
        // پاک کردن اطلاعات کاربر
        this.token = null;
        this.user = null;
        
        // انتقال به صفحه لاگین
        this.redirectToLogin();
    }

    redirectToLogin() {
        // اگر در صفحه لاگین نیستیم، به آن منتقل شویم
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
        // مخفی کردن تمام ویوها
        document.querySelectorAll('.view').forEach(view => {
            view.style.display = 'none';
        });
        
        // نمایش صفحه لاگین
        const loginView = document.getElementById('view-login');
        if (loginView) {
            loginView.style.display = 'block';
        }
        
        // مخفی کردن سایدبار و هدر
        const sidebar = document.getElementById('app-sidebar');
        const header = document.querySelector('.app-header');
        if (sidebar) sidebar.style.display = 'none';
        if (header) header.style.display = 'none';
        
        // تغییر استایل بدنه برای صفحه لاگین
        document.body.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
    }

    showMainApp() {
        // نمایش سایدبار و هدر
        const sidebar = document.getElementById('app-sidebar');
        const header = document.querySelector('.app-header');
        if (sidebar) sidebar.style.display = 'flex';
        if (header) header.style.display = 'flex';
        
        // بازگرداندن استایل بدنه
        document.body.style.background = '';
        
        // مخفی کردن صفحه لاگین
        const loginView = document.getElementById('view-login');
        if (loginView) {
            loginView.style.display = 'none';
        }
        
        // نمایش داشبورد به عنوان صفحه پیش‌فرض
        if (typeof navigateTo === 'function') {
            navigateTo('view-dashboard');
        }
    }
}

// ایجاد نمونه سراسری از مدیریت احراز هویت
window.authManager = new AuthManager();

// توابع کمکی برای استفاده در سایر بخش‌ها
window.requireAuth = function() {
    if (!window.authManager.isAuthenticated()) {
        window.authManager.redirectToLogin();
        return false;
    }
    return true;
};

window.requireAdmin = function() {
    if (!window.authManager.isAdmin()) {
        showToast('شما دسترسی لازم برای این عملیات را ندارید', 'error');
        return false;
    }
    return true;
};

// اضافه کردن دکمه خروج به منوی کاربر
document.addEventListener('DOMContentLoaded', function() {
    // ایجاد دکمه خروج اگر وجود ندارد
    const userDropdown = document.getElementById('user-dropdown');
    if (userDropdown) {
        // بررسی وجود دکمه خروج
        const logoutBtn = userDropdown.querySelector('.dropdown-item.text-danger');
        if (!logoutBtn) {
            // ایجاد دکمه خروج
            const logoutItem = document.createElement('a');
            logoutItem.href = '#';
            logoutItem.className = 'dropdown-item text-danger';
            logoutItem.innerHTML = '<span class="material-icons-round">logout</span> خروج';
            logoutItem.onclick = function(e) {
                e.preventDefault();
                window.authManager.logout();
            };
            
            // اضافه کردن به منوی کشویی
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
    const max429Retries = Number.isFinite(options.max429Retries) ? Number(options.max429Retries) : 2;
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
