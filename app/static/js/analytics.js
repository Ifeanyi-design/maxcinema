(() => {
    const sendEvent = (event, target = "") => {
        const payload = JSON.stringify({
            event,
            target,
            page: window.location.pathname
        });

        if (navigator.sendBeacon) {
            const blob = new Blob([payload], { type: "application/json" });
            navigator.sendBeacon("/track/event", blob);
            return;
        }

        fetch("/track/event", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
            keepalive: true
        }).catch(() => {});
    };

    const getDeviceType = () => window.matchMedia("(max-width: 767px)").matches ? "mobile" : "desktop";

    const trackAdSlots = () => {
        const slots = document.querySelectorAll("[data-ad-slot]");
        if (!slots.length) return;

        const seen = new Set();
        const markVisible = (el) => {
            const slot = (el.getAttribute("data-ad-slot") || "unknown").trim().toLowerCase();
            const eventKey = `${slot}|${getDeviceType()}`;
            if (seen.has(eventKey)) return;
            seen.add(eventKey);
            sendEvent("ad_slot_view", eventKey);
        };

        if (!("IntersectionObserver" in window)) {
            slots.forEach((slot) => markVisible(slot));
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                markVisible(entry.target);
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.35 });

        slots.forEach((slot) => observer.observe(slot));
    };

    document.addEventListener("click", (e) => {
        const downloadLink = e.target.closest(".download-ad-trigger");
        if (downloadLink) {
            sendEvent("download_click", downloadLink.getAttribute("href") || "");
            return;
        }

        const adSlot = e.target.closest("[data-ad-slot]");
        if (adSlot) {
            const slot = (adSlot.getAttribute("data-ad-slot") || "unknown").trim().toLowerCase();
            sendEvent("ad_slot_click", `${slot}|${getDeviceType()}`);
        }

        const shareButton = e.target.closest("#shareVideoBtn, #shareBtn");
        if (shareButton) {
            sendEvent("share_click", shareButton.id || "share_button");
        }
    });

    document.addEventListener("submit", (e) => {
        if (e.target.matches("#desktopSearch, #MobileSearch")) {
            sendEvent("search_submit", "header_search");
        } else if (e.target.matches("#movie-request-form")) {
            sendEvent("request_submit", "movie_request_form");
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", trackAdSlots);
    } else {
        trackAdSlots();
    }
})();
