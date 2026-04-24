// Minimal login-only entry point – no runtime bridges loaded.
void (async () => {
  await import("../legacy_runtime/loaders/login");
})();
