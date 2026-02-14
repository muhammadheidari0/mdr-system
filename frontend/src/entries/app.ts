import "./runtime";

const pathname = String(window.location.pathname || "").trim();

void (async () => {
  if (pathname === "/login") {
    await import("../legacy_runtime/loaders/login");
    return;
  }

  if (pathname === "/debug_login") {
    await import("../legacy_runtime/loaders/debug_login");
    return;
  }

  if (pathname === "/api/v1/mdr/bulk-register-page") {
    await import("../legacy_runtime/loaders/bulk_register");
    return;
  }

  await import("../legacy_runtime/loaders/main_shell");
})();
