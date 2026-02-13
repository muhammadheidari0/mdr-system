// Ù…Ù†Ø·Ù‚ Ù„Ø§Ú¯ÛŒÙ† Ø¨Ø±Ø§ÛŒ ØµÙØ­Ù‡ Ø§ÛŒØ²ÙˆÙ„Ù‡
        document.addEventListener('DOMContentLoaded', function() {
            const loginForm = document.getElementById('loginForm');
            const loginBtn = document.getElementById('loginBtn');
            const messageContainer = document.getElementById('message-container');
            
            if (!loginForm || !loginBtn) return;
            
            function showMessage(message, type = 'error') {
                messageContainer.innerHTML = `
                    <div class="${type}-message">
                        ${message}
                    </div>
                `;
                
                // Ù¾Ø§Ú© Ú©Ø±Ø¯Ù† Ù¾ÛŒØ§Ù… Ø¨Ø¹Ø¯ Ø§Ø² 5 Ø«Ø§Ù†ÛŒÙ‡
                setTimeout(() => {
                    messageContainer.innerHTML = '';
                }, 5000);
            }
            
            loginForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                
                if (!email || !password) {
                    showMessage('Ù„Ø·ÙØ§Ù‹ Ø§ÛŒÙ…ÛŒÙ„ Ùˆ Ø±Ù…Ø² Ø¹Ø¨ÙˆØ± Ø±Ø§ ÙˆØ§Ø±Ø¯ Ú©Ù†ÛŒØ¯', 'error');
                    return;
                }
                
                // Show loading state
                loginBtn.disabled = true;
                loginBtn.innerHTML = '<span class="material-icons-round">hourglass_empty</span> Ø¯Ø± Ø­Ø§Ù„ ÙˆØ±ÙˆØ¯...';
                
                try {
                    // Ø§Ø³ØªÙØ§Ø¯Ù‡ Ø§Ø² AuthManager Ø¨Ø±Ø§ÛŒ ÙˆØ±ÙˆØ¯
                    const result = await window.authManager.login(email, password);
                    
                    if (result.success) {
                        showMessage('ÙˆØ±ÙˆØ¯ Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯', 'success');
                        
                        // Redirect to dashboard after a short delay
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 1500);
                    } else {
                        showMessage(result.error || 'Ø®Ø·Ø§ Ø¯Ø± ÙˆØ±ÙˆØ¯ Ø¨Ù‡ Ø³ÛŒØ³ØªÙ…', 'error');
                    }
                    
                } catch (error) {
                    console.error('Login error:', error);
                    showMessage('Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙˆØ±', 'error');
                } finally {
                    // Hide loading state
                    loginBtn.disabled = false;
                    loginBtn.innerHTML = '<span class="material-icons-round">login</span> ÙˆØ±ÙˆØ¯ Ø¨Ù‡ Ø³ÛŒØ³ØªÙ…';
                }
            });
        });
