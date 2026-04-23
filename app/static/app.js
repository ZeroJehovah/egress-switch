(() => {
  const refreshDelayMs = 1500;
  const healthcheckIntervalMs = 2500;
  const healthcheckPath = "/healthz";
  const progressNode = document.querySelector("#switch-progress");
  const switchForms = document.querySelectorAll("[data-ajax-switch-form]");
  const nextSwitchForms = document.querySelectorAll("[data-ajax-switch-next-form]");

  if (switchForms.length === 0 && nextSwitchForms.length === 0) {
    return;
  }

  let switchInFlight = false;
  let healthcheckTimerId = null;

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
    if (!progressNode) {
      return;
    }
    progressNode.hidden = false;
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

  switchForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const targetIp = new FormData(form).get("target_ip");
      const body = new URLSearchParams({ target_ip: String(targetIp ?? "") });
      sendAjaxSwitch("/api/switch", body);
    });
  });

  nextSwitchForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      sendAjaxSwitch("/api/switch/next", new URLSearchParams());
    });
  });
})();
