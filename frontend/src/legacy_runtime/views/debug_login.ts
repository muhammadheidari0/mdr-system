// @ts-nocheck
const logDiv = document.getElementById("log");
const debugForm = document.getElementById("debugForm");

if (logDiv && debugForm) {
  function log(msg) {
    logDiv.innerHTML += `${msg}\n`;
    console.log(msg);
  }

  debugForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    log("Attempting login...");

    const email = document.getElementById("email")?.value;
    const password = document.getElementById("password")?.value;

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      log(`Status: ${res.status}`);

      const data = await res.json();
      log(`Response: ${JSON.stringify(data, null, 2)}`);

      if (res.ok) {
        log("LOGIN SUCCESS! Token received.");
        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("auth_last_activity_at", String(Date.now()));
        localStorage.setItem("auth_last_heartbeat_at", "0");
        log("Token saved to localStorage.");
        log("No auto redirect (debug mode).");
      } else {
        log("LOGIN FAILED.");
      }
    } catch (err) {
      log(`NETWORK ERROR: ${err?.message || err}`);
    }
  });
}

export {};
