// @ts-nocheck
/**
 * UIManager - Ù…ÙˆØªÙˆØ± Ù…Ø¯ÛŒØ±ÛŒØª Ù¾ÛŒØ§Ù… Ùˆ Ø®Ø·Ø§
 * Ø¬Ø§ÛŒÚ¯Ø²ÛŒÙ† alert() Ø¨Ø§ Toast Notifications Ù…Ø¯Ø±Ù†
 */
class UIManager {
    constructor() {
        // Ø§ÛŒØ¬Ø§Ø¯ Ú©Ø§Ù†ØªÛŒÙ†Ø± Ø¨Ø±Ø§ÛŒ Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ Ø§Ú¯Ø± ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯
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

        // Ø­Ø°Ù Ø®ÙˆØ¯Ú©Ø§Ø± Ø¨Ø¹Ø¯ Ø§Ø² 5 Ø«Ø§Ù†ÛŒÙ‡
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

    // Ù…Ø¯ÛŒØ±ÛŒØª ÙˆØ¶Ø¹ÛŒØª Ø¯Ú©Ù…Ù‡â€ŒÙ‡Ø§ (Loading)
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

// Ø§ÛŒØ¬Ø§Ø¯ ÛŒÚ© Ù†Ù…ÙˆÙ†Ù‡ Ú¯Ù„ÙˆØ¨Ø§Ù„
const UI = new UIManager();
window.UI = UI;

// Ù…ÛŒØ§Ù†Ø¨Ø±Ù‡Ø§ÛŒ Ú¯Ù„ÙˆØ¨Ø§Ù„ Ø¨Ø±Ø§ÛŒ Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø³Ø±ÛŒØ¹
window.showToast = (msg, type) => UI.showToast(msg, type);
window.showSuccess = (msg) => UI.success(msg);
window.showError = (msg) => UI.error(msg);
window.showInfo = (msg) => UI.info(msg);
window.showWarning = (msg) => UI.warning(msg);
