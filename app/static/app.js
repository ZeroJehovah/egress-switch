(() => {
  const refreshDelayMs = 1500;
  const healthcheckIntervalMs = 2500;
  const healthcheckPath = "/healthz";
  const themeStorageKey = "switch-ip-theme";

  const progressNode = document.querySelector("#switch-progress");
  const switchForms = document.querySelectorAll("[data-ajax-switch-form]");
  const searchInput = document.querySelector("[data-ip-search]");
  const ipRows = Array.from(document.querySelectorAll("[data-ip-row]"));
  const emptySearchNode = document.querySelector("[data-ip-empty]");
  const refreshButton = document.querySelector("[data-refresh-page]");
  const themeButton = document.querySelector("[data-theme-toggle]");

  let switchInFlight = false;
  let healthcheckTimerId = null;

  const syncThemeToggleState = (theme) => {
    if (!themeButton) {
      return;
    }

    const isNight = theme === "night";
    themeButton.setAttribute(
      "aria-label",
      isNight ? "当前为暗色模式，点击切换为亮色模式" : "当前为亮色模式，点击切换为暗色模式",
    );
    themeButton.setAttribute(
      "title",
      isNight ? "切换为亮色模式" : "切换为暗色模式",
    );
  };

  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(themeStorageKey, theme);
    syncThemeToggleState(theme);
  };

  const initializeTheme = () => {
    const savedTheme = window.localStorage.getItem(themeStorageKey);
    if (savedTheme === "night" || savedTheme === "light") {
      applyTheme(savedTheme);
      return;
    }

    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(prefersDark ? "night" : "light");
  };

  const setButtonsDisabled = (disabled) => {
    document.querySelectorAll("button").forEach((button) => {
      if (button.dataset.preserveDisabled === "true") {
        return;
      }

      if (disabled) {
        button.dataset.originalDisabled = button.disabled ? "true" : "false";
        button.disabled = true;
        return;
      }

      button.disabled = button.dataset.originalDisabled === "true";
    });
  };

  const showProgress = () => {
    if (progressNode) {
      progressNode.hidden = false;
    }
  };

  const startRefreshPolling = () => {
    const checkHealth = () => {
      fetch(healthcheckPath, {
        method: "GET",
        cache: "no-store",
        credentials: "same-origin",
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          window.location.reload();
        })
        .catch(() => {
          healthcheckTimerId = window.setTimeout(checkHealth, healthcheckIntervalMs);
        });
    };

    healthcheckTimerId = window.setTimeout(checkHealth, refreshDelayMs);
  };

  const sendAjaxSwitch = (url, body) => {
    if (switchInFlight) {
      return;
    }

    switchInFlight = true;
    showProgress();
    setButtonsDisabled(true);

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body,
      keepalive: true,
    }).catch(() => {
      // The proxy path may disconnect during IP switching. Ignore transport errors.
    });

    startRefreshPolling();
  };

  const updateSearchResults = () => {
    if (!searchInput || ipRows.length === 0) {
      return;
    }

    const keyword = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    ipRows.forEach((row) => {
      const value = (row.dataset.ipValue || "").toLowerCase();
      const visible = value.includes(keyword);
      row.hidden = !visible;
      if (visible) {
        visibleCount += 1;
      }
    });

    if (emptySearchNode) {
      emptySearchNode.hidden = visibleCount !== 0;
    }
  };

  initializeTheme();

  switchForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const targetIp = new FormData(form).get("target_ip");
      const body = new URLSearchParams({ target_ip: String(targetIp ?? "") });
      sendAjaxSwitch("/api/switch", body);
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", updateSearchResults);
    updateSearchResults();
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", () => {
      window.location.reload();
    });
  }

  if (themeButton) {
    themeButton.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "night" ? "light" : "night";
      applyTheme(nextTheme);
    });
  }

  window.addEventListener("beforeunload", () => {
    if (healthcheckTimerId !== null) {
      window.clearTimeout(healthcheckTimerId);
    }
  });
})();
