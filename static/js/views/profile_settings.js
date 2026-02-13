function profileNotify(type, message) {
    if (window.UI && typeof window.UI[type] === "function") {
        window.UI[type](message);
        return;
    }
    if (typeof showToast === "function") {
        showToast(message, type === "error" ? "error" : "success");
        return;
    }
    alert(message);
}

function openUserSettingsTab(tabName, btnEl) {
    document
        .querySelectorAll("#view-profile .user-settings-tab-btn")
        .forEach((button) => button.classList.remove("active"));
    document
        .querySelectorAll("#view-profile .user-settings-tab-content")
        .forEach((content) => content.classList.remove("active"));

    const button =
        btnEl || document.querySelector(`#view-profile .user-settings-tab-btn[data-user-tab="${tabName}"]`);
    if (button) button.classList.add("active");

    const target = document.getElementById(`user-tab-${tabName}`);
    if (target) target.classList.add("active");
}

function bindProfileSettingsActions() {
    const root = document.getElementById("view-profile");
    if (!root || root.dataset.boundProfileActions === "1") return;

    root.addEventListener("click", (event) => {
        const tabBtn = event.target.closest(".user-settings-tab-btn[data-user-tab]");
        if (tabBtn && root.contains(tabBtn)) {
            event.preventDefault();
            const tab = String(tabBtn.getAttribute("data-user-tab") || "").trim();
            if (tab) openUserSettingsTab(tab, tabBtn);
            return;
        }

        const actionBtn = event.target.closest("[data-profile-action]");
        if (!actionBtn || !root.contains(actionBtn)) return;
        event.preventDefault();

        const action = String(actionBtn.getAttribute("data-profile-action") || "").trim().toLowerCase();
        if (action === "change-password") {
            submitUserPasswordChange();
            return;
        }
        if (action === "logout") {
            window.authManager?.logout?.();
        }
    });

    root.dataset.boundProfileActions = "1";
}

async function loadUserProfileData() {
    try {
        const response = await fetchWithAuth("/api/v1/auth/me");
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "خطا در دریافت اطلاعات کاربری");
        }

        const user = await response.json();
        const roleMap = {
            admin: "مدیر سیستم",
            manager: "سرپرست",
            dcc: "کنترل مدارک (DCC)",
            user: "کاربر",
            viewer: "مشاهده‌گر",
        };
        const roleLabel = roleMap[String(user.role || "").toLowerCase()] || "کاربر";
        const activeLabel = user.is_active ? "فعال" : "غیرفعال";

        document.getElementById("profile-email").value = user.email || "-";
        document.getElementById("profile-full-name").value = user.full_name || "-";
        document.getElementById("profile-role").value = roleLabel;
        document.getElementById("profile-status").value = activeLabel;
        document.getElementById("profile-security-active").textContent = activeLabel;
    } catch (error) {
        console.error("loadUserProfileData error:", error);
        profileNotify("error", "دریافت اطلاعات کاربری انجام نشد");
    }
}

async function submitUserPasswordChange() {
    const currentPasswordEl = document.getElementById("profile-current-password");
    const newPasswordEl = document.getElementById("profile-new-password");
    const confirmPasswordEl = document.getElementById("profile-confirm-password");
    const submitBtn = document.getElementById("profile-password-btn");

    const currentPassword = currentPasswordEl.value.trim();
    const newPassword = newPasswordEl.value.trim();
    const confirmPassword = confirmPasswordEl.value.trim();

    if (!currentPassword || !newPassword || !confirmPassword) {
        profileNotify("error", "لطفا همه فیلدهای رمز عبور را تکمیل کنید");
        return;
    }
    if (newPassword.length < 8) {
        profileNotify("error", "رمز عبور جدید باید حداقل 8 کاراکتر باشد");
        return;
    }
    if (newPassword !== confirmPassword) {
        profileNotify("error", "تکرار رمز عبور با رمز جدید یکسان نیست");
        return;
    }

    if (window.UI && typeof window.UI.setBtnLoading === "function") {
        window.UI.setBtnLoading(submitBtn, true);
    } else {
        submitBtn.disabled = true;
    }

    try {
        const response = await fetchWithAuth("/api/v1/auth/change-password", {
            method: "POST",
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
            }),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            profileNotify("error", data.detail || "تغییر رمز عبور انجام نشد");
            return;
        }

        currentPasswordEl.value = "";
        newPasswordEl.value = "";
        confirmPasswordEl.value = "";
        profileNotify("success", data.message || "رمز عبور با موفقیت تغییر کرد");
    } catch (error) {
        console.error("submitUserPasswordChange error:", error);
        profileNotify("error", "خطای شبکه در تغییر رمز عبور");
    } finally {
        if (window.UI && typeof window.UI.setBtnLoading === "function") {
            window.UI.setBtnLoading(submitBtn, false);
        } else {
            submitBtn.disabled = false;
        }
    }
}

function initUserSettingsView() {
    bindProfileSettingsActions();
    openUserSettingsTab("account");
    loadUserProfileData();
}

window.openUserSettingsTab = openUserSettingsTab;
window.initUserSettingsView = initUserSettingsView;
window.submitUserPasswordChange = submitUserPasswordChange;
