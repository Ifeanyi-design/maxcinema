document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("recentlyViewedSection");
    const grid = document.getElementById("recentlyViewedGrid");
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
            <a href="${safeUrl}" class="group block flex-none w-[86px] md:w-[108px] bg-white rounded-md overflow-hidden shadow-sm hover:shadow-lg transition-all border border-gray-100 hover:-translate-y-0.5">
                <div class="relative aspect-[2/3] bg-gray-100">
                    <img src="${safeImage}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    <span class="absolute top-1 right-1 text-[8px] font-black uppercase bg-black/80 text-white px-1.5 py-0.5 rounded">${safeType}</span>
                </div>
                <div class="p-1">
                    <p class="text-[10px] font-bold text-gray-900 line-clamp-2 leading-tight">${safeTitle}</p>
                    <p class="text-[8px] text-gray-500 font-bold mt-0.5">${safeYear}</p>
                </div>
            </a>
        `;
    }).join("");

    section.classList.remove("hidden");

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
