(function () {
  function bootGlobalDocSearch() {
    if (typeof window.DocSearch === "function") {
      new window.DocSearch("globalDocSearchInput");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootGlobalDocSearch);
  } else {
    bootGlobalDocSearch();
  }
})();
