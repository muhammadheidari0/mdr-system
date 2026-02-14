// @ts-nocheck
function initLoginStandalone() {
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginBtn');
    const messageContainer = document.getElementById('message-container');
    if (!loginForm || !loginBtn || !messageContainer) return;
    if (loginForm.dataset.bound === '1') return;
    loginForm.dataset.bound = '1';

    function showMessage(message, type = 'error') {
        messageContainer.innerHTML = `
            <div class="${type}-message">
                ${message}
            </div>
        `;
        setTimeout(() => {
            messageContainer.innerHTML = '';
        }, 5000);
    }

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const email = String(document.getElementById('email')?.value || '').trim();
        const password = String(document.getElementById('password')?.value || '').trim();
        if (!email || !password) {
            showMessage('لطفاً ایمیل و رمز عبور را وارد کنید', 'error');
            return;
        }

        loginBtn.disabled = true;
        loginBtn.innerHTML = '<span class="material-icons-round">hourglass_empty</span> در حال ورود...';

        try {
            const result = await window.authManager.login(email, password);
            if (result?.success) {
                showMessage('ورود با موفقیت انجام شد', 'success');
                setTimeout(() => {
                    window.location.href = '/';
                }, 800);
                return;
            }
            showMessage(result?.error || 'ورود ناموفق بود. اطلاعات را بررسی کنید.', 'error');
        } catch (error) {
            console.error('Login error:', error);
            showMessage('خطا در ارتباط با سرور', 'error');
        } finally {
            loginBtn.disabled = false;
            loginBtn.innerHTML = '<span class="material-icons-round">login</span> ورود به سیستم';
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLoginStandalone, { once: true });
} else {
    initLoginStandalone();
}

export {};
