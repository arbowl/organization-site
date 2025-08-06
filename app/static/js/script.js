document.addEventListener('DOMContentLoaded', () => {
    // Reply toggle for comments
    document.querySelectorAll('.reply-toggle').forEach(btn => {
        btn.addEventListener('click', e => {
            e.preventDefault();
            const id = btn.dataset.comment;
            const replyForm = document.getElementById(`reply-${id}`);
            if (replyForm) {
                replyForm.style.display = 'block';
            }
        });
    });

    // EasyMDE Markdown Editor (for post content)
    const contentField = document.getElementById('post-content');
    if (contentField) {
        const easyMDE = new EasyMDE({ element: contentField });

        const charCountSpan = document.getElementById('char-count');
        const maxCharsSpan = document.getElementById('max-chars');
        const maxLength = contentField.getAttribute('maxlength');

        if (maxCharsSpan && maxLength) {
            maxCharsSpan.textContent = maxLength;
        }

        function updateCharCount() {
            const currentLength = easyMDE.value().length;
            if (charCountSpan) {
                charCountSpan.textContent = currentLength;
                charCountSpan.style.color = currentLength > maxLength ? 'red' : '';
            }
        }

        updateCharCount();
        easyMDE.codemirror.on("change", updateCharCount);
    }

    // Post-level share button
    const shareButton = document.getElementById("share-button");
    if (shareButton) {
        shareButton.addEventListener("click", async () => {
            const url = window.location.href;

            if (navigator.share) {
                try {
                    await navigator.share({
                        title: document.title,
                        url: url
                    });
                    return;
                } catch (err) {
                    console.error("Native share failed:", err);
                }
            }

            if (navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(url);
                    showCopiedFeedback(shareButton);
                    return;
                } catch (err) {
                    console.error("Clipboard API failed:", err);
                }
            }

            try {
                const textarea = document.createElement("textarea");
                textarea.value = url;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
                showCopiedFeedback(shareButton);
            } catch (err) {
                console.error("Fallback copy failed:", err);
                alert("Unable to share. Please copy the URL manually.");
            }
        });
    }

    // Comment-level share buttons
    document.querySelectorAll(".comment-share-button").forEach(button => {
        button.addEventListener("click", async () => {
            const commentId = button.dataset.commentId;
            const commentUrl = `${window.location.origin}${window.location.pathname}#c${commentId}`;

            if (navigator.share) {
                try {
                    await navigator.share({
                        title: document.title,
                        url: commentUrl
                    });
                    return;
                } catch (err) {
                    console.error("Native comment share failed:", err);
                }
            }

            if (navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(commentUrl);
                    showCopiedFeedback(button);
                    return;
                } catch (err) {
                    console.error("Clipboard API failed:", err);
                }
            }

            try {
                const textarea = document.createElement("textarea");
                textarea.value = commentUrl;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
                showCopiedFeedback(button);
            } catch (err) {
                console.error("Fallback comment copy failed:", err);
                alert("Unable to share. Please copy the comment URL manually.");
            }
        });
    });

    function showCopiedFeedback(buttonElement) {
        const originalHTML = buttonElement.innerHTML;
        buttonElement.innerHTML = "✅ Copied!";
        setTimeout(() => {
            buttonElement.innerHTML = originalHTML;
        }, 2000);
    }

    document.querySelectorAll('.reply-form textarea').forEach(textarea => {
        const charCountSpan = document.getElementById(`char-count-${textarea.closest('form').id.split('-')[1]}`);
        const maxCharsSpan = document.getElementById(`max-chars-${textarea.closest('form').id.split('-')[1]}`);
        const maxLength = 5000; // Max characters for comment

        if (charCountSpan && maxCharsSpan) {
            maxCharsSpan.textContent = maxLength;
        }

        function updateCharCount() {
            const currentLength = textarea.value.length;
            if (charCountSpan) {
                charCountSpan.textContent = currentLength;
                charCountSpan.style.color = currentLength > maxLength ? 'red' : ''; // Red color if over max length
            }
        }

        // Update on typing
        updateCharCount();
        textarea.addEventListener("input", updateCharCount);
    });
});