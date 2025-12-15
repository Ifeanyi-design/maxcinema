function showCommentNotification(message = "Comment posted!") {
    const notif = document.getElementById('comment-notification');
    notif.textContent = message;
    notif.classList.add('show');

    setTimeout(() => notif.classList.remove('show'), 2000);
}

document.addEventListener('click', function(e) {

    // Open reply box
    if (e.target.classList.contains('reply-btn')) {
        let parentId = e.target.dataset.id;
        let videoId = e.target.dataset.video;

        // Insert new reply box
        e.target.insertAdjacentHTML('afterend', `
            <div class="reply-box px-5 mt-4 flex flex-col gap-5 slide-fade-enter">
                <div>
                    <legend>Name</legend>
                    <input type="text" class="reply-name w-full bg-gray-200 rounded-md h-[7vh] p-2" placeholder="Your name">
                </div>
                <div>
                    <legend>Email</legend>
                    <input type="email" class="reply-email w-full bg-gray-200 rounded-md h-[7vh] p-2" placeholder="Your email">
                </div>
                <div>
                    <legend>Comment</legend>
                    <textarea class="reply-text w-full bg-gray-200 rounded-md h-[20vh] p-2" placeholder="Reply..."></textarea>
                </div>
                <div class="flex gap-3">
                    <button class="send-reply py-2 w-40 bg-red-600 rounded-lg hover:bg-red-700 hover:text-white transition text-white" data-parent="${parentId}" data-video="${videoId}">Send</button>
                    <button class="cancel-reply py-2 w-40 bg-gray-400 rounded-lg hover:bg-gray-500 transition text-white">Cancel</button>
                </div>
            </div>
        `);

        let box = e.target.nextElementSibling;
        // Trigger slide-fade animation
        requestAnimationFrame(() => box.classList.add('slide-fade-enter-active'));
    }

    // Cancel reply
    if (e.target.classList.contains('cancel-reply')) {
        let replyBox = e.target.closest('.reply-box');
        replyBox.classList.remove('slide-fade-enter-active');
        replyBox.classList.add('slide-fade-exit-active');
        setTimeout(() => replyBox.remove(), 300);
    }

    // Submit reply
    if (e.target.classList.contains('send-reply')) {
        let parentId = e.target.dataset.parent;
        let videoId = e.target.dataset.video;
        let replyBox = e.target.closest('.reply-box');

        let name = replyBox.querySelector('.reply-name').value;
        let email = replyBox.querySelector('.reply-email').value;
        let text = replyBox.querySelector('.reply-text').value;

        fetch(`/comment/reply/${videoId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                name, email, text, parent_id: parentId
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let parentDiv = document.querySelector(`.reply-btn[data-id='${parentId}']`).closest('div.flex.flex-col');
                let repliesDiv = parentDiv.querySelector('.replies');

                if (!repliesDiv) {
                    repliesDiv = document.createElement('div');
                    repliesDiv.classList.add('replies', 'ml-6', 'flex', 'flex-col', 'gap-2');
                    parentDiv.appendChild(repliesDiv);
                }

                // Insert new reply with slide-fade
                let tempDiv = document.createElement('div');
                tempDiv.innerHTML = data.html;
                let newReply = tempDiv.firstElementChild;
                newReply.classList.add('slide-fade-enter');
                repliesDiv.appendChild(newReply);

                requestAnimationFrame(() => newReply.classList.add('slide-fade-enter-active'));

                // Remove reply input box
                replyBox.remove();

                // Show notification
                showCommentNotification("Reply posted!");
            } else {
                alert('Something went wrong. Please try again.');
            }
        })
        .catch(err => console.error(err));
    }
});




// Main comment submission
document.getElementById('main-comment-form').addEventListener('submit', function(e) {
    e.preventDefault();

    let form = e.target;
    let videoId = form.dataset.videoId;
    let formData = new URLSearchParams(new FormData(form));

    fetch(`/comment/add/${videoId}`, { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let tempDiv = document.createElement('div');
                tempDiv.innerHTML = data.html;
                let newComment = tempDiv.firstElementChild;

                newComment.classList.add('slide-fade-enter');

                let container = document.getElementById('comments-container');
                container.prepend(newComment);

                requestAnimationFrame(() => newComment.classList.add('slide-fade-enter-active'));

                form.reset();

                // Show notification
                showCommentNotification();
            } else {
                alert('Something went wrong. Try again.');
            }
        })
        .catch(err => console.error(err));
});

// // Reply submission
// document.addEventListener('click', function(e) {
//     if (e.target.classList.contains('send-reply')) {
//         let parentId = e.target.dataset.parent;
//         let videoId = e.target.dataset.video;
//         let replyBox = e.target.closest('.reply-box');

//         let name = replyBox.querySelector('.reply-name').value;
//         let email = replyBox.querySelector('.reply-email').value;
//         let text = replyBox.querySelector('.reply-text').value;

//         fetch(`/comment/reply/${videoId}`, {
//             method: 'POST',
//             headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
//             body: new URLSearchParams({ name, email, text, parent_id: parentId })
//         })
//         .then(res => res.json())
//         .then(data => {
//             if (data.success) {
//                 let parentDiv = document.querySelector(`.reply-btn[data-id='${parentId}']`).closest('div.flex.flex-col');
//                 let repliesDiv = parentDiv.querySelector('.replies');

//                 if (!repliesDiv) {
//                     repliesDiv = document.createElement('div');
//                     repliesDiv.classList.add('replies', 'ml-6', 'flex', 'flex-col', 'gap-2');
//                     parentDiv.appendChild(repliesDiv);
//                 }

//                 let tempDiv = document.createElement('div');
//                 tempDiv.innerHTML = data.html;
//                 let newReply = tempDiv.firstElementChild;

//                 newReply.classList.add('slide-fade-enter');
//                 repliesDiv.appendChild(newReply);

//                 requestAnimationFrame(() => newReply.classList.add('slide-fade-enter-active'));

//                 replyBox.remove();

//                 // Show notification
//                 showCommentNotification("Reply posted!");
//             } else {
//                 alert('Something went wrong. Please try again.');
//             }
//         })
//         .catch(err => console.error(err));
//     }
// });
