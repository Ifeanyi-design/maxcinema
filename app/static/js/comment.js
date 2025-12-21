// --- NOTIFICATION SYSTEM ---
function showNotification(message, type = 'normal') {
    // Select the correct ID based on the page type
    const notifId = type === 'trailer' ? 'trailer-comment-notification' : 'comment-notification';
    const notif = document.getElementById(notifId);
    
    if (notif) {
        notif.textContent = message;
        notif.classList.add('show');
        // Hide after 3 seconds
        setTimeout(() => notif.classList.remove('show'), 3000);
    } else {
        console.warn("Notification element not found:", notifId);
    }
}

// --- MAIN COMMENT SUBMISSION ---
document.addEventListener('submit', function(e) {
    // Check if the submitted form is EITHER the main one OR the trailer one
    if (e.target.matches('#main-comment-form, #trailer-main-comment-form')) {
        e.preventDefault();
        handleCommentSubmit(e.target);
    }
});

function handleCommentSubmit(form) {
    let videoId = form.dataset.videoId;
    // Check if we are on a trailer page based on the Form ID
    let isTrailer = form.id.includes('trailer'); 
    
    let typePath = isTrailer ? '/trailer' : ''; 
    let containerId = isTrailer ? 'trailer-comments-container' : 'comments-container';
    
    let formData = new URLSearchParams(new FormData(form));

    fetch(`/comment/add/${videoId}${typePath}`, { 
        method: 'POST', 
        body: formData 
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            let tempDiv = document.createElement('div');
            tempDiv.innerHTML = data.html;
            let newComment = tempDiv.firstElementChild;

            // Animation class
            newComment.classList.add('slide-fade-enter');
            
            // Add to the list
            let container = document.getElementById(containerId);
            if(container) {
                container.prepend(newComment);
                // Trigger animation
                requestAnimationFrame(() => newComment.classList.add('slide-fade-enter-active'));
            }

            form.reset();
            // Show the correct notification
            showNotification("Comment posted!", isTrailer ? 'trailer' : 'normal');
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => console.error(err));
}

// --- REPLY SYSTEM ---
document.addEventListener('click', function(e) {
    
    // 1. OPEN REPLY BOX
    if (e.target.matches('.reply-btn, .trailer-reply-btn') || e.target.closest('.reply-btn, .trailer-reply-btn')) {
        // Handle clicking the icon or the button
        let btn = e.target.closest('button'); 
        let parentId = btn.dataset.id;
        let videoId = btn.dataset.video;
        let isTrailer = btn.classList.contains('trailer-reply-btn');
        
        // Dark mode styles for input
        let inputBg = isTrailer ? 'bg-gray-200 dark:bg-gray-700 dark:text-white' : 'bg-gray-200';
        // Class to identify the box later
        let boxClass = isTrailer ? 'trailer-reply-box' : 'reply-box';

        // HTML Template for the reply box
        // FIX: Cancel button is now Light Gray with Black text so it's visible in Dark Mode
        let replyHtml = `
            <div class="${boxClass} px-5 mt-4 flex flex-col gap-5 slide-fade-enter">
                <div><legend class="${isTrailer ? 'dark:text-white' : ''}">Name</legend><input type="text" class="r-name w-full ${inputBg} rounded-md h-[7vh] p-2" placeholder="Name"></div>
                <div><legend class="${isTrailer ? 'dark:text-white' : ''}">Email</legend><input type="email" class="r-email w-full ${inputBg} rounded-md h-[7vh] p-2" placeholder="Email"></div>
                <div><legend class="${isTrailer ? 'dark:text-white' : ''}">Comment</legend><textarea class="r-text w-full ${inputBg} rounded-md h-[20vh] p-2" placeholder="Reply..."></textarea></div>
                <div class="flex gap-3">
                    <button class="do-reply py-2 w-40 bg-red-600 rounded-lg text-white hover:bg-red-700" 
                        data-parent="${parentId}" data-video="${videoId}" data-trailer="${isTrailer}">Send</button>
                    <button class="cancel-reply py-2 w-40 bg-gray-300 rounded-lg text-black hover:bg-gray-400 font-semibold">Cancel</button>
                </div>
            </div>`;

        btn.insertAdjacentHTML('afterend', replyHtml);
        let box = btn.nextElementSibling;
        requestAnimationFrame(() => box.classList.add('slide-fade-enter-active'));
    }

    // 2. CANCEL REPLY
    if (e.target.classList.contains('cancel-reply')) {
        let box = e.target.closest('div[class*="reply-box"]');
        box.classList.remove('slide-fade-enter-active');
        box.classList.add('slide-fade-exit-active');
        setTimeout(() => box.remove(), 300);
    }

    // 3. SEND REPLY
    if (e.target.classList.contains('do-reply')) {
        let btn = e.target;
        let parentId = btn.dataset.parent;
        let videoId = btn.dataset.video;
        let isTrailer = btn.dataset.trailer === 'true';
        let box = btn.closest('div[class*="reply-box"]');

        let name = box.querySelector('.r-name').value;
        let email = box.querySelector('.r-email').value;
        let text = box.querySelector('.r-text').value;

        let typePath = isTrailer ? '/trailer' : '';

        fetch(`/comment/reply/${videoId}${typePath}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ name, email, text, parent_id: parentId })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // Find parent container to append reply
                let btnSelector = isTrailer ? `.trailer-reply-btn[data-id='${parentId}']` : `.reply-btn[data-id='${parentId}']`;
                let parentBtn = document.querySelector(btnSelector);
                let parentCard = parentBtn.closest('div.flex.flex-col');
                
                // Find or create replies container
                let repliesDivClass = isTrailer ? 'trailer-replies' : 'replies';
                let repliesDiv = parentCard.querySelector('.' + repliesDivClass);
                
                if (!repliesDiv) {
                    repliesDiv = document.createElement('div');
                    repliesDiv.className = `${repliesDivClass} ml-6 flex flex-col gap-2`;
                    parentCard.appendChild(repliesDiv);
                }

                let tempDiv = document.createElement('div');
                tempDiv.innerHTML = data.html;
                let newReply = tempDiv.firstElementChild;
                
                newReply.classList.add('slide-fade-enter');
                repliesDiv.appendChild(newReply);
                requestAnimationFrame(() => newReply.classList.add('slide-fade-enter-active'));

                box.remove();
                showNotification("Reply posted!", isTrailer ? 'trailer' : 'normal');
            } else {
                alert(data.error || 'Error posting reply');
            }
        })
        .catch(err => console.error(err));
    }
});