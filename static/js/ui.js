/**
 * UIManager - موتور مدیریت پیام و خطا
 * جایگزین alert() با Toast Notifications مدرن
 */
class UIManager {
    constructor() {
        // ایجاد کانتینر برای پیام‌ها اگر وجود ندارد
        if (!document.getElementById('toast-container')) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            document.body.appendChild(this.container);
        } else {
            this.container = document.getElementById('toast-container');
        }
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = 'info';
        if (type === 'success') icon = 'check_circle';
        if (type === 'error') icon = 'error';
        if (type === 'warning') icon = 'warning_amber';

        const iconEl = document.createElement('span');
        iconEl.className = 'material-icons-round toast-icon';
        iconEl.textContent = icon;

        const messageEl = document.createElement('span');
        messageEl.style.flex = '1';
        messageEl.textContent = String(message ?? '');

        const closeEl = document.createElement('span');
        closeEl.className = 'material-icons-round';
        closeEl.style.cursor = 'pointer';
        closeEl.style.fontSize = '18px';
        closeEl.style.opacity = '0.6';
        closeEl.textContent = 'close';
        closeEl.addEventListener('click', () => toast.remove());

        toast.appendChild(iconEl);
        toast.appendChild(messageEl);
        toast.appendChild(closeEl);

        this.container.appendChild(toast);

        // حذف خودکار بعد از 5 ثانیه
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('hide');
                toast.addEventListener('animationend', () => toast.remove());
            }
        }, 5000);
    }

    success(msg) { this.showToast(msg, 'success'); }
    error(msg) { this.showToast(msg, 'error'); }
    warning(msg) { this.showToast(msg, 'warning'); }
    info(msg) { this.showToast(msg, 'info'); }

    // مدیریت وضعیت دکمه‌ها (Loading)
    setBtnLoading(btn, status) {
        if (!btn) return;
        if (status) {
            btn.classList.add('loading');
            btn.dataset.originalText = btn.innerText;
        } else {
            btn.classList.remove('loading');
        }
    }
}

// ایجاد یک نمونه گلوبال
const UI = new UIManager();
window.UI = UI;

// میانبرهای گلوبال برای استفاده سریع
window.showToast = (msg, type) => UI.showToast(msg, type);
window.showSuccess = (msg) => UI.success(msg);
window.showError = (msg) => UI.error(msg);
window.showInfo = (msg) => UI.info(msg);
window.showWarning = (msg) => UI.warning(msg);
