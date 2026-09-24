(() => {
    const storageKey = "cale-shop-theme";
    const root = document.documentElement;

    let savedTheme = "light";
    try {
        savedTheme = localStorage.getItem(storageKey) || "light";
    } catch (_) {
        // Keep the site usable when browser storage is unavailable.
    }

    const applyTheme = (theme) => {
        root.dataset.theme = theme;
        root.style.colorScheme = theme;
    };

    applyTheme(savedTheme === "dark" ? "dark" : "light");

    document.addEventListener("DOMContentLoaded", () => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "theme-toggle";
        button.setAttribute("aria-pressed", String(root.dataset.theme === "dark"));
        button.addEventListener("click", () => {
            const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
            applyTheme(nextTheme);
            button.setAttribute("aria-pressed", String(nextTheme === "dark"));
            try {
                localStorage.setItem(storageKey, nextTheme);
            } catch (_) {
                // The current page still changes theme if storage is unavailable.
            }
            updateButton();
        });

        function updateButton() {
            const isDark = root.dataset.theme === "dark";
            button.textContent = isDark ? "☀️ الوضع الفاتح" : "🌙 الوضع الداكن";
            button.setAttribute("aria-label", isDark ? "تفعيل الوضع الفاتح" : "تفعيل الوضع الداكن");
            button.setAttribute("aria-pressed", String(isDark));
        }

        updateButton();
        const placement = document.querySelector(".header-top-inner, .admin-user, .auth-card");
        if (placement) {
            placement.append(button);
        } else {
            document.body.append(button);
        }
    });
})();
