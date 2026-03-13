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
        return `
            <a href="${safeUrl}" class="group block flex-none w-[84px] md:w-[100px] bg-white rounded-md overflow-hidden shadow-sm hover:shadow-md transition-all border border-gray-100 hover:-translate-y-0.5">
                <div class="relative h-[108px] md:h-[126px] bg-gray-100">
                    <img src="${safeImage}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                </div>
                <div class="p-1">
                    <div class="flex items-center justify-between gap-1 mb-0.5">
                        <span class="text-[7px] font-black uppercase bg-gray-900 text-white px-1 py-[1px] rounded">${safeType}</span>
                        <span class="text-[8px] text-gray-500 font-bold">${safeYear}</span>
                    </div>
                    <p class="text-[10px] font-bold text-gray-900 line-clamp-1 leading-tight">${safeTitle}</p>
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
