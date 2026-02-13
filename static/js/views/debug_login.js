const logDiv = document.getElementById('log');
    function log(msg) {
        logDiv.innerHTML += msg + "\n";
        console.log(msg);
    }

    document.getElementById('debugForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        log("ðŸš€ Attempting login...");
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;

        try {
            const res = await fetch('/api/v1/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            log(`ðŸ“¡ Status: ${res.status}`);
            
            const data = await res.json();
            log(`ðŸ“¦ Response: ${JSON.stringify(data, null, 2)}`);

            if (res.ok) {
                log("âœ… LOGIN SUCCESS! Token received.");
                localStorage.setItem('access_token', data.access_token);
                log("ðŸ’¾ Token saved to LocalStorage.");
                log("âš ï¸ I will NOT redirect automatically to prevent loops.");
            } else {
                log("âŒ LOGIN FAILED.");
            }

        } catch (err) {
            log(`ðŸ”¥ NETWORK ERROR: ${err.message}`);
        }
    });
