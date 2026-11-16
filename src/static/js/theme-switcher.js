(function () {
  function syncThemeColor(mode) {
    document
      .querySelectorAll('meta[name="theme-color"]')
      .forEach((el) => el.remove());

    const head = document.head;
    const add = (content, media) => {
      const meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      meta.setAttribute("content", content);
      if (media) meta.setAttribute("media", media);
      head.appendChild(meta);
    };

    if (mode === "light") {
      add("#eef1f5");
      return;
    }
    if (mode === "system") {
      add("#181a1b", "(prefers-color-scheme: dark)");
      add("#eef1f5", "(prefers-color-scheme: light)");
      return;
    }
    add("#181a1b");
  }

  function applyTheme(mode) {
    document.documentElement.setAttribute("data-theme", mode);
    syncThemeColor(mode);
    const preferenceSelect = document.getElementById("preference-theme");
    if (preferenceSelect && preferenceSelect.value !== mode) {
      preferenceSelect.value = mode;
    }
    window.dispatchEvent(
      new CustomEvent("mediatrail:themechange", { detail: { theme: mode } }),
    );
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("themeSwitcher", (config) => ({
      theme: config.theme || "dark",
      url: config.url,
      csrfToken: config.csrfToken,
      saveFailed: config.saveFailed || "Could not save the theme.",
      busy: false,
      menuOpen: false,
      statusMessage: "",

      init() {
        applyTheme(this.theme);
      },

      async setTheme(next) {
        if (this.busy) {
          return;
        }
        if (next === this.theme) {
          this.menuOpen = false;
          return;
        }
        const previous = this.theme;
        this.theme = next;
        this.statusMessage = "";
        applyTheme(next);
        this.busy = true;
        try {
          const body = new FormData();
          body.append("theme", next);
          body.append("csrfmiddlewaretoken", this.csrfToken);
          const response = await fetch(this.url, {
            method: "POST",
            body,
            headers: {
              Accept: "application/json",
              "X-Requested-With": "XMLHttpRequest",
            },
            credentials: "same-origin",
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || !data.ok) {
            throw new Error(data.error || this.saveFailed);
          }
          this.theme = data.theme || next;
          applyTheme(this.theme);
          this.menuOpen = false;
        } catch (error) {
          this.theme = previous;
          applyTheme(previous);
          this.statusMessage = error.message || this.saveFailed;
        } finally {
          this.busy = false;
        }
      },
    }));
  });
})();
