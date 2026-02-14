// @ts-nocheck
(function () {
  function callGlobal(fnName) {
    var fn = window[fnName];
    if (typeof fn !== "function") {
      return false;
    }
    var args = Array.prototype.slice.call(arguments, 1);
    fn.apply(window, args);
    return true;
  }

  function handleFabUploadClick() {
    callGlobal("navigateTo", "view-edms");
    setTimeout(function () {
      callGlobal("openEdmsTab", "archive");
      var archivePanel = document.getElementById("view-archive");
      if (!archivePanel || archivePanel.style.display === "none") {
        return;
      }
      callGlobal("archiveOpenModal");
    }, 220);
  }

  function bindContextMenuHandlers() {
    var items = document.querySelectorAll("#context-menu [data-context-action]");
    items.forEach(function (item) {
      item.addEventListener("click", function () {
        var action = item.getAttribute("data-context-action");
        if (action) {
          callGlobal("handleAction", action);
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var overlay = document.getElementById("sidebar-overlay");
    if (overlay) {
      overlay.addEventListener("click", function () {
        callGlobal("toggleSidebar");
      });
    }

    var fabUploadBtn = document.getElementById("fab-upload-btn");
    if (fabUploadBtn) {
      fabUploadBtn.addEventListener("click", handleFabUploadClick);
    }

    bindContextMenuHandlers();
  });
})();
