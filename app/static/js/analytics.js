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

    document.addEventListener("click", (e) => {
        const downloadLink = e.target.closest(".download-ad-trigger");
        if (downloadLink) {
            sendEvent("download_click", downloadLink.getAttribute("href") || "");
            return;
        }

        const shareButton = e.target.closest("#shareVideoBtn, #shareBtn");
        if (shareButton) {
            sendEvent("share_click", shareButton.id || "share_button");
            return;
        }

        const socialCta = e.target.closest('a[data-social-cta]');
        if (socialCta) {
            sendEvent("social_cta_click", socialCta.getAttribute("href") || "");
        }
    });

    document.addEventListener("submit", (e) => {
        if (e.target.matches("#desktopSearch, #MobileSearch")) {
            sendEvent("search_submit", "header_search");
        } else if (e.target.matches("#movie-request-form")) {
            sendEvent("request_submit", "movie_request_form");
        }
    });
})();
