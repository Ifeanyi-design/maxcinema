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
            ? `<span style="position:absolute;top:4px;right:4px;font-size:8px;font-weight:900;text-transform:uppercase;background:rgba(0,0,0,.75);color:#fff;padding:1px 6px;border-radius:4px;">${safeType}</span>`
            : "";
        return `
            <a href="${safeUrl}" class="group block flex-none bg-white rounded-md overflow-hidden shadow-sm hover:shadow-md transition-all border border-gray-100" style="width:86px;">
                <div class="relative bg-gray-100" style="height:118px;">
                    <img src="${safeImage}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    ${typeBadge}
                </div>
                <div style="padding:6px;">
                    <div class="flex items-center justify-end" style="margin-bottom:2px;">
                        <span style="font-size:9px;color:#6b7280;font-weight:700;">${safeYear}</span>
                    </div>
                    <p style="font-size:11px;font-weight:700;color:#111827;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${safeTitle}</p>
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
