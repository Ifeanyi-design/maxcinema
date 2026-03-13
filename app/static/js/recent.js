document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("recentlyViewedSection");
    const grid = document.getElementById("recentlyViewedGrid");
    const body = document.getElementById("recentlyViewedBody");
    const toggleBtn = document.getElementById("recentToggleBtn");
    const leftBtn = document.getElementById("recentScrollLeft");
    const rightBtn = document.getElementById("recentScrollRight");
    if (!section || !grid) return;

    let items = [];
    try {
        items = JSON.parse(localStorage.getItem("maxcinema_recently_viewed") || "[]");
    } catch (err) {
        items = [];
    }

    if (!Array.isArray(items) || items.length === 0) return;

    const maxItems = 8;
    const visible = items.slice(0, maxItems);
    grid.innerHTML = visible.map((item) => {
        const safeTitle = (item.title || "Untitled").replace(/"/g, "&quot;");
        const safeType = (item.type || "").toUpperCase();
        const safeYear = item.year || "";
        const safeImage = item.image || "";
        const safeUrl = item.url || "#";
        const typeBadge = safeType
            ? `<span class="recent-type-badge">${safeType}</span>`
            : "";
        return `
            <a href="${safeUrl}" class="recent-card group block flex-none bg-white overflow-hidden shadow-sm hover:shadow-md transition-all border border-gray-100">
                <div class="recent-poster">
                    <img src="${safeImage}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    ${typeBadge}
                </div>
                <div class="recent-meta">
                    <div class="recent-year-wrap">
                        <span class="recent-year">${safeYear}</span>
                    </div>
                    <p class="recent-title">${safeTitle}</p>
                </div>
            </a>
        `;
    }).join("");

    section.classList.remove("hidden");

    const collapsedKey = "maxcinema_recent_collapsed";
    const applyCollapsedState = (collapsed) => {
        if (!body || !toggleBtn) return;
        body.classList.toggle("hidden", collapsed);
        toggleBtn.textContent = collapsed ? "Show" : "Hide";
    };

    if (toggleBtn && body) {
        const isCollapsed = localStorage.getItem(collapsedKey) === "1";
        applyCollapsedState(isCollapsed);
        toggleBtn.addEventListener("click", () => {
            const current = localStorage.getItem(collapsedKey) === "1";
            const next = !current;
            localStorage.setItem(collapsedKey, next ? "1" : "0");
            applyCollapsedState(next);
        });
    }

    if (leftBtn && rightBtn) {
        const scrollAmount = () => Math.max(220, Math.floor(grid.clientWidth * 0.7));
        const refreshButtons = () => {
            const maxLeft = Math.max(0, grid.scrollWidth - grid.clientWidth);
            const atStart = grid.scrollLeft <= 2;
            const atEnd = grid.scrollLeft >= (maxLeft - 2);
            leftBtn.disabled = atStart;
            rightBtn.disabled = atEnd;
            leftBtn.classList.toggle("opacity-40", atStart);
            rightBtn.classList.toggle("opacity-40", atEnd);
        };
        leftBtn.addEventListener("click", () => {
            grid.scrollBy({ left: -scrollAmount(), behavior: "smooth" });
        });
        rightBtn.addEventListener("click", () => {
            grid.scrollBy({ left: scrollAmount(), behavior: "smooth" });
        });
        grid.addEventListener("scroll", refreshButtons, { passive: true });
        window.addEventListener("resize", refreshButtons);
        refreshButtons();
    }
});
