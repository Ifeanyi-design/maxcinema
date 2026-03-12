document.addEventListener("DOMContentLoaded", () => {
    const section = document.getElementById("recentlyViewedSection");
    const grid = document.getElementById("recentlyViewedGrid");
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
            <a href="${safeUrl}" class="group block bg-white rounded-xl overflow-hidden shadow-sm hover:shadow-lg transition-all border border-gray-100">
                <div class="relative aspect-[2/3] bg-gray-100">
                    <img src="${safeImage}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    <span class="absolute top-2 right-2 text-[9px] font-black uppercase bg-black/80 text-white px-2 py-0.5 rounded">${safeType}</span>
                </div>
                <div class="p-2">
                    <p class="text-xs font-bold text-gray-900 line-clamp-2">${safeTitle}</p>
                    <p class="text-[10px] text-gray-500 font-bold mt-1">${safeYear}</p>
                </div>
            </a>
        `;
    }).join("");

    section.classList.remove("hidden");
});

