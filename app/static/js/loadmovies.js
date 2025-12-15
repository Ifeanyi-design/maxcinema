// Your JSON data
const movieData = { "featured": [ {"title": "Stranger Things", "poster": "https://i.redd.it/ctc98gifegyf1.jpeg"}, {"title": "The Mandalorian", "poster": "https://pbs.twimg.com/media/G5AofDDWUAAaOhO.jpg"}, {"title": "House of the Dragon", "poster": "https://i.redd.it/4tpzzc0ht6791.jpg"}, {"title": "Black Panther: Wakanda Forever", "poster": "https://image.tmdb.org/t/p/w500/ps2oKfhY6DL3alynlSqY97gHSsg.jpg"}, {"title": "Guardians of the Galaxy Vol. 3", "poster": "https://pbs.twimg.com/media/GyToZt_aEAAL8Ln.jpg"}, {"title": "The Last of Us", "poster": "https://i.redd.it/3evpud14bvpe1.jpeg"}, {"title": "The Flash", "poster": "https://i.redd.it/syxqjbyoz1wa1.jpg"}, {"title": "Loki", "poster": "https://pbs.twimg.com/media/GBF3sY9WIAA3prr.jpg"} ], "trending_movies": [ {"title": "Barbie", "poster": "https://i.redd.it/w1hmtffyjs7b1.jpg"}, {"title": "Oppenheimer", "poster": "https://i.redd.it/4nj1l524d1ya1.jpg"}, {"title": "Spider-Man: Across the Spider-Verse", "poster": "https://i.redd.it/u14ntorg727a1.jpg"}, {"title": "John Wick: Chapter 4", "poster": "https://i.redd.it/0domq0vf0zha1.jpg"}, {"title": "Mission: Impossible – Dead Reckoning Part One", "poster": "https://i.redd.it/oalg073ddpna1.jpg"}, {"title": "Transformers: Rise of the Beasts", "poster": "https://i.redd.it/nccquqv3lb3a1.jpg"}, {"title": "The Marvels", "poster": "https://i.redd.it/kzn1xwxws8db1.jpg"}, {"title": "The Hunger Games: The Ballad of Songbirds & Snakes", "poster": "https://i.redd.it/d4kf4vluhepb1.jpg"} ], "trending_series": [ {"title": "Wednesday", "poster": "https://i.redd.it/8hud7jbt50pf1.jpeg"}, {"title": "The Witcher", "poster": "https://i.redd.it/mvk3oqgia1pf1.jpeg"}, {"title": "Arcane", "poster": "https://i.redd.it/ntexla4yfthd1.jpeg"}, {"title": "Better Call Saul", "poster": "https://i.redd.it/f9n4gno9npm81.jpg"}, {"title": "The Boys", "poster": "https://i.redd.it/0oc5y0yx36kc1.jpeg"}, {"title": "Succession", "poster": "https://i.redd.it/2p918jkyan2b1.jpg"}, {"title": "Severance", "poster": "https://preview.redd.it/luqyg2wgjwpe1.jpeg?width=3024&format=pjpg&auto=webp&s=c56239cb93ce600f2b3a0767c9bd64a489e40ade"}, {"title": "House of Cards", "poster": "https://i.imgur.com/TrZdIrI.png"} ], "recently_added": [ {"title": "The Batman", "poster": "https://image.tmdb.org/t/p/w500/74xTEgt7R36Fpooo50r9T25onhq.jpg"}, {"title": "Avatar: The Way of Water", "poster": "https://image.tmdb.org/t/p/w500/t6HIqrRAclMCA60NsSmeqe9RmNV.jpg"}, {"title": "Thor: Love and Thunder", "poster": "https://image.tmdb.org/t/p/w500/pIkRyD18kl4FhoCNQuWxWu5cBLM.jpg"}, {"title": "Black Adam", "poster": "https://image.tmdb.org/t/p/w500/pFlaoHTZeyNkG83vxsAJiGzfSsa.jpg"}, {"title": "Doctor Strange in the Multiverse of Madness", "poster": "https://image.tmdb.org/t/p/w500/9Gtg2DzBhmYamXBS1hKAhiwbBKS.jpg"}, {"title": "Ant-Man and the Wasp: Quantumania", "poster": "https://image.tmdb.org/t/p/w500/ngl2FKBlU4fhbdsrtdom9LVLBXw.jpg"}, {"title": "Spider-Man: No Way Home", "poster": "https://image.tmdb.org/t/p/w500/1g0dhYtq4irTY1GPXvft6k4YLjm.jpg"}, {"title": "Everything Everywhere All at Once", "poster": "https://image.tmdb.org/t/p/w500/woTQx9Q4b8aO13jR9dsj8C9JESy.jpg"}, {"title": "Past Lives", "poster": "https://image.tmdb.org/t/p/w500/k3waqVXSnvCZWfJYNtdamTgTtTA.jpg"}, {"title": "Asteroid City", "poster": "https://pbs.twimg.com/media/Fw_VVS_WcAE7zj_.jpg"}, {"title": "Dune: Part Two", "poster": "https://pbs.twimg.com/media/GgYDqdVWYAAYzod.jpg"}, {"title": "The Little Mermaid", "poster": "https://image.tmdb.org/t/p/w500/ym1dxyOk4jFcSl4Q2zmRrA5BEEN.jpg"}, {"title": "The Marvels", "poster": "https://image.tmdb.org/t/p/w500/9GBhzXMFjgcZ3FdR9w3bUMMTps5.jpg"}, {"title": "Transformers: Rise of the Beasts", "poster": "https://image.tmdb.org/t/p/w500/gPbM0MK8CP8A174rmUwGsADNYKD.jpg"}, {"title": "Mission: Impossible – Dead Reckoning Part One", "poster": "https://image.tmdb.org/t/p/w500/NNxYkU70HPurnNCSiCjYAmacwm.jpg"}, {"title": "The Hunger Games: The Ballad of Songbirds & Snakes", "poster": "https://pbs.twimg.com/media/F8Z9X9jawAAb2rt.jpg"}, {"title": "Avatar", "poster": "https://image.tmdb.org/t/p/w500/jRXYjXNq0Cs2TcJjLkki24MLp7u.jpg"}, {"title": "Batman Returns", "poster": "https://pbs.twimg.com/media/GW5TPVPbMAAv8Ed.jpg"}, {"title": "Black Panther", "poster": "https://image.tmdb.org/t/p/w500/uxzzxijgPIY7slzFvMotPv8wjKA.jpg"}, {"title": "Shang-Chi and the Legend of the Ten Rings", "poster": "https://pbs.twimg.com/media/FuWrrqtXsAE3HmQ.jpg"}, {"title": "Guardians of the Galaxy", "poster": "https://image.tmdb.org/t/p/w500/r7vmZjiyZw9rpJMQJdXpjgiCOk9.jpg"}, {"title": "Iron Man", "poster": "https://image.tmdb.org/t/p/w500/78lPtwv72eTNqFW9COBYI0dWDJa.jpg"}, {"title": "Deadpool & Wolverine", "poster": "https://pbs.twimg.com/media/GTgmUaXbkAAhf-n.jpg"}, {"title": "Inside Out 2", "poster": "https://www.liveforfilm.com/wp-content/uploads/2024/03/inside_out_two-poster.jpg"} ], "trending_trailers": [ {"title": "The Running Man", "poster": "https://www.themoviedb.org/t/p/w600_and_h900_bestv2/bnGKTYXVkQp0TKWRfAvTTY1y2XC.jpg", "trailer": "https://www.youtube.com/watch?v=KD18ddeFuyM"}, {"title": "Zootopia 2", "poster": "https://media.themoviedb.org/t/p/w300_and_h450_bestv2/oJ7g2CifqpStmoYQyaLQgEU32qO.jpg", "trailer": "https://www.youtube.com/watch?v=5AwtptT8X8k"}, {"title": "Predator: Badlands", "poster": "https://media.themoviedb.org/t/p/w300_and_h450_bestv2/sMybEeAn3aFXsIUUcWPSFXlS6qS.jpg", "trailer": "https://www.youtube.com/watch?v=43R9l7EkJwE"}, {"title": "Wicked: For Good", "poster": "https://media.themoviedb.org/t/p/w300_and_h450_bestv2/si9tolnefLSUKaqQEGz1bWArOaL.jpg", "trailer": "https://www.youtube.com/watch?v=vt98AlBDI9Y"}, {"title": "The Family Plan 2", "poster": "https://media.themoviedb.org/t/p/w300_and_h450_bestv2/semFxuYx6HcrkZzslgAkBqfJvZk.jpg", "trailer": "https://www.youtube.com/watch?v=dqolYtJGuf4"}, {"title": "Nuremberg", "poster": "https://image.tmdb.org/t/p/w500/5kpo8Cxqx6HQU1hY8yB43kZ7ZXg.jpg", "trailer": "https://www.youtube.com/watch?v=WvAy9C-bipY"}, {"title": "Wake Up Dead Man: A Knives Out Mystery", "poster": "https://www.impawards.com/2025/posters/wake_up_dead_man_a_knives_out_mystery.jpg", "trailer": "https://www.youtube.com/watch?v=eHM1K1JByBI"}, {"title": "Sisu 2: Road to Revenge", "poster": "https://www.impawards.com/intl/finland/2025/posters/sisu_road_to_revenge.jpg", "trailer": "https://www.youtube.com/watch?v=VmStqCXIgio"} ]};
function updateSection(sectionClass, dataArray, background=false) {
  const boxes = document.querySelectorAll(sectionClass);
  var n = 0;
  boxes.forEach((box, index) => {
    if (dataArray[index]) {
        if(background){
            
            const title = box.querySelector("h3");
            if (title) title.textContent = dataArray[index].title;
            const realbox = box.querySelector(".usedbg")
            realbox.style.backgroundImage = `url('${dataArray[index].poster}')`
        }
        else{
            const img = box.querySelector("img");
            const title = box.querySelector("h3");
            if (img) img.src = dataArray[index].poster;
            if (title) title.textContent = dataArray[index].title;
        }
      
    }
    else{
      if(background){
            if(dataArray.length >= n){
              const title = box.querySelector("h3");
              if (title) title.textContent = dataArray[n].title;
              const realbox = box.querySelector(".usedbg")
              realbox.style.backgroundImage = `url('${dataArray[n].poster}')`
              n+=1;
              }
            else{
              n=0;
            }
            
        }
        else{
          if(n < dataArray.length){
             const img = box.querySelector("img");
            const title = box.querySelector("h3");
            if (img) img.src = dataArray[n].poster;
            if (title) title.textContent = dataArray[n].title;
            n+=1;
          }
          else{
            n=0
          }
           
        }
    }
  });
}

// Update all sections
updateSection(".featureBox", movieData.featured, true);
updateSection(".trendingBoxes", movieData.recently_added, true);
updateSection(".trending-movies", movieData.trending_movies, true);
updateSection(".trending-series", movieData.trending_series, true);
updateSection(".trailers", movieData.trending_trailers, true);
updateSection(".recentBox", movieData.recently_added, false);
updateSection(".trailersAll", movieData.trending_trailers, false);

// Populate related placeholders: update existing HTML cards (image + title). If there's no data, show default boxes.
(function populateRelatedPlaceholders(){
  const relatedContainer = document.getElementById('relatedList');
  if (!relatedContainer) return;

  // source data preference
  const source = movieData.recently_added && movieData.recently_added.length ? movieData.recently_added : (movieData.featured && movieData.featured.length ? movieData.featured : []);

  // pick up to 6 items (deterministic by title using a simple hash shuffle)
  function hashStringToSeed(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
    return h >>> 0;
  }
  function seededShuffle(arr, seed){
    const out = arr.slice();
    let state = seed >>> 0;
    function rand(){ state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return (state >>> 0) / 4294967295; }
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }

  const pageTitle = document.querySelector('h2')?.textContent?.trim() || document.title || 'movie';
  const sourceFiltered = source.filter(s => (s.title || '').toLowerCase() !== pageTitle.toLowerCase());
  const items = sourceFiltered.length ? seededShuffle(sourceFiltered, hashStringToSeed(pageTitle)).slice(0,6) : [];

  const placeholders = Array.from(relatedContainer.querySelectorAll('.related-card'));

  function createCardElement(item) {
    const card = document.createElement('a');
    card.href = item && item.id ? `/movie.html?id=${item.id}` : '#';
    card.className = 'related-card block rounded overflow-hidden shadow-sm bg-white hover:shadow-lg transition-transform transform hover:-translate-y-1';

    const imgWrap = document.createElement('div');
    imgWrap.className = 'card-img w-full aspect-[2/3] bg-center bg-cover flex items-center justify-center';
    if (item && item.poster) imgWrap.style.backgroundImage = `url('${item.poster}')`;
    else imgWrap.style.backgroundColor = '#f3f4f6';

    const noData = document.createElement('div');
    noData.className = 'no-data text-gray-400 text-xs';
    noData.textContent = item ? '' : 'No data';
    if (!item) noData.classList.remove('hidden'); else noData.classList.add('hidden');
    imgWrap.appendChild(noData);

    const title = document.createElement('div');
    title.className = 'card-title p-2 text-sm font-semibold text-black line-clamp-2';
    title.textContent = item && item.title ? item.title : (item ? 'Untitled' : 'No recommendations');

    card.appendChild(imgWrap);
    card.appendChild(title);
    return card;
  }

  // Update placeholders and create extra cards if more items than placeholders
  placeholders.forEach((card, idx) => {
    const item = items[idx];
    const imgWrap = card.querySelector('.card-img');
    const titleEl = card.querySelector('.card-title');
    const noDataEl = card.querySelector('.no-data');
    if (item) {
      if (imgWrap) {
        imgWrap.style.backgroundImage = `url('${item.poster}')`;
        imgWrap.style.backgroundColor = '';
      }
      if (titleEl) titleEl.textContent = item.title || 'Untitled';
      if (noDataEl) noDataEl.classList.add('hidden');
      if (item.id) card.href = `/movie.html?id=${item.id}`;
    } else {
      if (imgWrap) {
        imgWrap.style.backgroundImage = '';
        imgWrap.style.backgroundColor = '#f3f4f6';
      }
      if (titleEl) titleEl.textContent = 'No recommendations';
      if (noDataEl) {
        noDataEl.textContent = 'No data';
        noDataEl.classList.remove('hidden');
      }
      card.href = '#';
    }
  });

  // If there are more items than placeholders, append additional cards
  if (items.length > placeholders.length) {
    for (let i = placeholders.length; i < items.length; i++) {
      const item = items[i];
      const newCard = createCardElement(item);
      relatedContainer.appendChild(newCard);
    }
  }
})();