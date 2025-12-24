const gerneBtn = document.getElementById("gerneBtn");
const gerneModal = document.getElementById("genreMenu");
    const featureContainer = document.getElementById("featurecontain");
const scrollRight = document.getElementById("ScrollRight");
const scrollLeft = document.getElementById("ScrollLeft");
const searchBtn = document.getElementById("SearchBtn");
const desksearchContainer = document.getElementById("desktopSearch");
const desksearchInput = document.getElementById("SearchInput");
const genreNav = document.getElementById("MobilegenreNav");
const menuBtn = document.querySelector(".menu-btn");
const hamburger = document.querySelector(".menu-btn-burger");
const nav = document.querySelector(".nav");
const navMenu = document.querySelector(".menu-nav");
const MobileSearchBtn = document.getElementById("MobileSearchBtn")
const MobileSearch = document.getElementById("MobileSearch")
const MobileSearchInput = document.getElementById("MobileSearchInput")

let showMe = false;



function toggleMenu(){
    if(!showMe){
        hamburger.classList.add("open")
        nav.classList.add("open")
        navMenu.classList.add("open")
        showMe = true;
    }else{
        hamburger.classList.remove("open")
        nav.classList.remove("open")
        navMenu.classList.remove("open")
        showMe = false;
    }
}
menuBtn.addEventListener("click", toggleMenu);

const toggleGenreMenu = ()=>{
    gerneModal.classList.toggle("hiddennav");
    gerneModal.classList.toggle("hidden");
    gerneModal.classList.toggle("pointer-events-auto");
    gerneModal.classList.toggle("pointer-events-none");
};

const closeGenreMenu = () =>{
    gerneModal.classList.remove("hiddennav");
    gerneModal.classList.add("hidden");
    gerneModal.classList.remove("pointer-events-auto");
    gerneModal.classList.add("pointer-events-none");
}

gerneBtn.addEventListener("mouseenter", toggleGenreMenu);

gerneBtn.addEventListener("mouseleave", (e)=>{
    setTimeout(()=>{
        if(!gerneModal.matches(":hover") && !gerneBtn.matches(":hover")){
            closeGenreMenu();
        }
    }, 100);
})

gerneModal.addEventListener("mouseleave", (e)=>{
    setTimeout(()=>{
        if(!gerneModal.matches(":hover") && !gerneBtn.matches(":hover")){
            closeGenreMenu();
        }
    }, 100);
})


// Safe scrolling handlers: only wire up if the expected elements exist
if (featureContainer && (scrollLeft || scrollRight)) {
    let scrollInterval;

    function startScroll(direction){
        stopScroll();
        // featureContainer guaranteed to exist in this block
        scrollInterval = setInterval(()=>{
            featureContainer.scrollBy({left: direction === "left"? -10 : 10, behavior: "auto"});
        }, 10);
    }

    function stopScroll(){
        clearInterval(scrollInterval)
    }

    if (scrollLeft) scrollLeft.addEventListener("mousedown", ()=>startScroll("left"));
    if (scrollRight) scrollRight.addEventListener("mousedown", ()=>startScroll("right"));
    document.addEventListener("mouseup", stopScroll);
    document.addEventListener("mouseleave", stopScroll);

    if (scrollLeft) {
        scrollLeft.addEventListener("click", ()=>{
            featureContainer.scrollBy({left: -300, behavior: "smooth"})
        });
    }

    if (scrollRight) {
        scrollRight.addEventListener("click", ()=>{
            featureContainer.scrollBy({left: 300, behavior: "smooth"})
        });
    }
}




searchBtn.addEventListener("click", ()=>{
    desksearchContainer.classList.toggle("hidden");
    desksearchContainer.classList.toggle("flex");
    desksearchInput.focus();
});
MobileSearchBtn.addEventListener("click", ()=>{
    MobileSearch.classList.toggle("hidden");
    MobileSearch.classList.toggle("flex");
    MobileSearchInput.focus();
});

document.addEventListener("click", (e)=>{
    if(!searchBtn.contains(e.target) && !desksearchContainer.contains(e.target) && !desksearchInput.contains(e.target)){
        desksearchContainer.classList.add("hidden");
        desksearchContainer.classList.remove("flex");
    }
})


genreNav.scrollTo({ left: 60, behavior: 'smooth' });
setTimeout(() => genreNav.scrollTo({ left: 0, behavior: 'smooth' }), 500);

document.addEventListener("click", (e)=>{
    if(!menuBtn.contains(e.target) && !nav.contains(e.target)){
        hamburger.classList.remove("open")
        nav.classList.remove("open")
        navMenu.classList.remove("open")
        showMe = false;
    }
});

document.addEventListener("click", (e) => {
    const mobileSearch = document.getElementById("MobileSearch");
    const mobileSearchInput = document.getElementById("MobileSearchInput");
    const searchIcon = document.getElementById("MobileSearchBtn"); // if you have a search icon button

    if (
        !MobileSearch.contains(e.target) &&
        !MobileSearchBtn.contains(e.target)
    ) {
        MobileSearch.classList.add("hidden");   // hide the search container
        MobileSearch.classList.remove("flex");  // remove flex if you’re using it to show
    }
});

// -------------------------
// Star rating widget
// -------------------------
// (function () {
//     const starContainer = document.getElementById('starRating');
//     if (!starContainer) return; // not a movie page

//     const stars = Array.from(starContainer.querySelectorAll('.star'));
//     const ratingValueDisplay = document.getElementById('ratingValue');

//     // Use page title or heading as a key to persist rating per-movie (sanitized)
//     const pageTitle = document.querySelector('h2')?.textContent?.trim() || document.title || 'movie';
//     const storageKey = 'maxcinema_rating_' + pageTitle.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_\-]/g, '');

//     function setRating(rating) {
//         stars.forEach((s) => {
//             const val = Number(s.dataset.value || 0);
//             if (val <= rating) {
//                 s.classList.remove('text-gray-300');
//                 s.classList.add('text-yellow-400');
//                 s.setAttribute('aria-checked', 'true');
//             } else {
//                 s.classList.remove('text-yellow-400');
//                 s.classList.add('text-gray-300');
//                 s.setAttribute('aria-checked', 'false');
//             }
//         });
//         if (ratingValueDisplay) {
//             ratingValueDisplay.textContent = rating ? `You rated ${rating}/5` : 'Not rated';
//         }
//         try {
//             localStorage.setItem(storageKey, String(rating || 0));
//         } catch (err) {
//             // ignore storage errors
//             console.warn('Could not persist rating', err);
//         }
//     }

//     // Initialize from storage
//     const initial = Number(localStorage.getItem(storageKey)) || 0;
//     setRating(initial);

//     // Hover behavior
//     stars.forEach((star) => {
//         const value = Number(star.dataset.value || 0);
//         star.addEventListener('mouseenter', () => {
//             stars.forEach((s) => {
//                 const v = Number(s.dataset.value || 0);
//                 if (v <= value) {
//                     s.classList.remove('text-gray-300');
//                     s.classList.add('text-yellow-400');
//                 } else {
//                     s.classList.remove('text-yellow-400');
//                     s.classList.add('text-gray-300');
//                 }
//             });
//         });

//         star.addEventListener('mouseleave', () => {
//             // restore persisted rating
//             const saved = Number(localStorage.getItem(storageKey)) || 0;
//             setRating(saved);
//         });

//         star.addEventListener('click', () => {
//             const saved = Number(localStorage.getItem(storageKey)) || 0;
//             const newRating = value === saved ? 0 : value; // clicking same rating clears
//             setRating(newRating);
//         });
//     });
// })();


// (function () {
//     const container = document.getElementById('starRating');
//     if (!container) return;

//     const stars = Array.from(container.querySelectorAll('.star'));
//     const ratingValueDisplay = document.getElementById('ratingValue');
//     const videoId = container.dataset.videoId;

//     let currentRating = 0; // stores the rating user clicked

//     function updateStars(rating) {
//         stars.forEach(s => {
//             const val = Number(s.dataset.value);
//             if (val <= rating) {
//                 s.classList.remove('text-gray-300');
//                 s.classList.add('text-yellow-400');
//             } else {
//                 s.classList.remove('text-yellow-400');
//                 s.classList.add('text-gray-300');
//             }
//         });
//     }

//     function updateRatingUI(data) {
//         ratingValueDisplay.textContent = `${data.average_rating} / 5 (${data.num_votes} votes)`;

//         for (let i = 1; i <= 5; i++) {
//             const bar = document.querySelector(`#breakdown .flex:nth-child(${6-i}) .rating-bar`);
//             const pct = data.num_votes ? (data.breakdown[i]/data.num_votes*100) : 0;
//             bar.style.width = pct + '%';
//         }
//     }

//     stars.forEach(star => {
//         const val = Number(star.dataset.value);

//         // Hover preview
//         star.addEventListener('mouseenter', () => updateStars(val));
//         star.addEventListener('mouseleave', () => updateStars(currentRating)); // restore current rating

//         // Click to set rating
//         star.addEventListener('click', () => {
//             fetch(`/rate/${videoId}`, {
//                 method: 'POST',
//                 headers: {'Content-Type': 'application/json'},
//                 body: JSON.stringify({rating: val})
//             })
//             .then(res => res.json())
//             .then(data => {
//                 currentRating = val;          // Update local clicked rating
//                 updateStars(currentRating);   // Reflect immediately in UI
//                 updateRatingUI(data);         // Update average + breakdown
//             });
//         });
//     });

//     // Initialize UI with existing rating from backend
//     fetch(`/rate/${videoId}`, {
//         method: 'GET'
//     })
//     .then(res => res.json())
//     .then(data => {
//         currentRating = Math.round(data.average_rating); // show stars approx
//         updateStars(currentRating);
//         updateRatingUI(data);
//     });

// })();

// document.addEventListener('DOMContentLoaded', () => {
//     const container = document.getElementById('starRating');
//     if (!container) return;

//     const stars = Array.from(container.querySelectorAll('.star'));
//     const ratingValueDisplay = document.getElementById('ratingValue');
//     const averageRatingDisplay = document.getElementById('averageRating');
//     const videoId = container.dataset.videoId;
//     const storageKey = `video_rating_${videoId}`;

//     let currentRating = 0;

//     function updateStars(rating) {
//         stars.forEach(s => {
//             const val = Number(s.dataset.value);
//             if (val <= rating) {
//                 s.classList.remove('text-gray-300');
//                 s.classList.add('text-yellow-400');
//             } else {
//                 s.classList.remove('text-yellow-400');
//                 s.classList.add('text-gray-300');
//             }
//         });
//     }

//     function updateRatingUI(data) {
//         if (ratingValueDisplay) {
//             ratingValueDisplay.textContent = `${data.average_rating.toFixed(1)} / 5 (${data.num_votes} votes)`;
//         }
//         if (averageRatingDisplay) {
//             averageRatingDisplay.textContent = data.average_rating.toFixed(1);
//             // Update number of votes as well
//             const votesEl = averageRatingDisplay.nextElementSibling;
//             if (votesEl) {
//                 votesEl.textContent = `(${data.num_votes} votes)`;
//             }
//         }
//     }

//     stars.forEach(star => {
//         const val = Number(star.dataset.value);

//         // Hover preview
//         star.addEventListener('mouseenter', () => updateStars(val));
//         star.addEventListener('mouseleave', () => updateStars(currentRating));

//         // Click to set rating
//         star.addEventListener('click', () => {
//             fetch(`/rate/${videoId}`, {
//                 method: 'POST',
//                 headers: {'Content-Type': 'application/json'},
//                 body: JSON.stringify({rating: val})
//             })
//             .then(res => res.json())
//             .then(data => {
//                 currentRating = val;
//                 updateStars(currentRating);
//                 updateRatingUI(data);

//                 // Save user's own rating in localStorage
//                 localStorage.setItem(storageKey, val);
//             })
//             .catch(err => console.error('Rating error:', err));
//         });
//     });

//     // Initialize UI
//     const savedRating = localStorage.getItem(storageKey);

//     fetch(`/rate/${videoId}`, { method: 'GET' })
//         .then(res => res.json())
//         .then(data => {
//             currentRating = savedRating ? Number(savedRating) : Math.round(data.average_rating);
//             updateStars(currentRating);
//             updateRatingUI(data);
//         })
//         .catch(err => console.error('Fetch rating error:', err));
// });

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('starRating');
    if (!container) return;

    const stars = Array.from(container.querySelectorAll('.star'));
    const ratingValueDisplay = document.getElementById('ratingValue');
    const averageRatingDisplay = document.getElementById('averageRating');
    const videoId = container.dataset.videoId;
    const storageKey = `video_rating_${videoId}`;

    let currentRating = 0;

    function updateStars(rating, isUser = false) {
        const targetRating = parseFloat(rating);
        stars.forEach(star => {
            const starValue = parseFloat(star.getAttribute('data-value'));
            star.classList.remove('full', 'half');

            if (isUser || currentRating > 0) {
                // If there's a user rating, fill all stars up to that point
                if (starValue <= targetRating) star.classList.add('full');
            } else {
                // Average rating logic
                if (starValue <= Math.floor(targetRating)) {
                    star.classList.add('full');
                } else if (starValue - 0.5 <= targetRating) {
                    star.classList.add('half');
                }
            }
        });
    }

    // --- STEP 1: Immediate Load from LocalStorage ---
    const savedRating = localStorage.getItem(storageKey);
    if (savedRating) {
        currentRating = parseFloat(savedRating);
        updateStars(currentRating, true);
        if (ratingValueDisplay) ratingValueDisplay.textContent = "Your rating saved";
    }

    // --- STEP 2: Fetch Server Data ---
    fetch(`/rate/${videoId}`, { method: 'GET' })
        .then(res => res.json())
        .then(data => {
            // Update Numbers
            if (averageRatingDisplay) averageRatingDisplay.textContent = data.average_rating.toFixed(1);
            
            // Only update icons if user HAS NOT rated yet
            if (!savedRating) {
                updateStars(data.average_rating, false);
            }
        })
        .catch(err => console.error('Fetch error:', err));

    // --- STEP 3: Click Listeners ---
    stars.forEach(star => {
        const val = star.getAttribute('data-value');
        
        star.addEventListener('mouseenter', () => updateStars(val, true));
        star.addEventListener('mouseleave', () => updateStars(currentRating || 0, currentRating > 0));

        star.addEventListener('click', () => {
            fetch(`/rate/${videoId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({rating: parseFloat(val)})
            })
            .then(res => res.json())
            .then(data => {
                currentRating = parseFloat(val);
                localStorage.setItem(storageKey, val);
                updateStars(currentRating, true);
                if (averageRatingDisplay) averageRatingDisplay.textContent = data.average_rating.toFixed(1);
            });
        });
    });
});
