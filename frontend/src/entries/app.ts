const pathname = String(window.location.pathname || "").trim();

void (async () => {
  // Login pages: skip runtime bridges entirely for faster load
  if (pathname === "/login") {
    await import("../legacy_runtime/loaders/login");
    return;
  }

  if (pathname === "/debug_login") {
    await import("../legacy_runtime/loaders/debug_login");
    return;
  }

  // All other pages need the full runtime bridges
  await import("./runtime");

  if (pathname === "/api/v1/mdr/bulk-register-page") {
    await import("../legacy_runtime/loaders/bulk_register");
    return;
  }

  await import("../legacy_runtime/loaders/main_shell");
})();
