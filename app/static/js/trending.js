document.querySelectorAll(".TrendingSection").forEach(wrapper => {
    const container = wrapper.querySelector(".trendingcontain");
    const leftBtn = wrapper.querySelector(".ScrollTrendingLeft");
    const rightBtn = wrapper.querySelector(".ScrollTrendingRight");

    let scrollInterval;

    function startScroll(direction) {
        stopScroll();
        scrollInterval = setInterval(() => {
            container.scrollBy({ left: direction === "left" ? -10 : 10, behavior: "auto" });
        }, 10);
    }

    function stopScroll() {
        clearInterval(scrollInterval);
    }

    if (leftBtn) {
        leftBtn.addEventListener("mousedown", ()=>startScroll("left"));
        leftBtn.addEventListener("mouseup", stopScroll);
        leftBtn.addEventListener("mouseleave", stopScroll);
        leftBtn.addEventListener("click", ()=>container.scrollBy({left:-300,behavior:"smooth"}));
    }

    if (rightBtn) {
        rightBtn.addEventListener("mousedown", ()=>startScroll("right"));
        rightBtn.addEventListener("mouseup", stopScroll);
        rightBtn.addEventListener("mouseleave", stopScroll);
        rightBtn.addEventListener("click", ()=>container.scrollBy({left:300,behavior:"smooth"}));
    }
    document.addEventListener("mouseup", stopScroll);
    document.addEventListener("mouseleave", stopScroll);
});
