document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.reply-toggle').forEach(btn => {
        btn.addEventListener('click', e => {
            e.preventDefault();
            const id = btn.dataset.comment;
            document.getElementById(`reply-${id}`).style.display = 'block';
        });
    });
    const easyMDE = new EasyMDE({ element: document.getElementById('post-content') });
    const charCountSpan = document.getElementById('char-count');
    const maxCharsSpan = document.getElementById('max-chars');
    const contentField = document.getElementById('post-content');
    const maxLength = contentField.getAttribute('maxlength');

    if (maxCharsSpan && maxLength) {
        maxCharsSpan.textContent = maxLength;
    }

    function updateCharCount() {
        const currentLength = easyMDE.value().length;
        charCountSpan.textContent = currentLength;

        if (currentLength > maxLength) {
            charCountSpan.style.color = 'red';
        } else {
            charCountSpan.style.color = '';
        }
    }
    updateCharCount();
    easyMDE.codemirror.on("change", updateCharCount);
});

document.addEventListener("DOMContentLoaded", function () {
    const shareButton = document.getElementById("share-button");

    shareButton.addEventListener("click", async () => {
        const url = window.location.href;

        // Try native share on mobile
        if (navigator.share) {
            try {
                await navigator.share({
                    title: document.title,
                    url: url
                });
                return;
            } catch (err) {
                console.error("Native share failed:", err);
                // Continue to clipboard fallback
            }
        }

        // Clipboard API (secure contexts only)
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(url);
                showCopiedFeedback();
                return;
            } catch (err) {
                console.error("Clipboard API failed:", err);
                // Continue to fallback method
            }
        }

        // Fallback for older/unsupported browsers
        try {
            const textarea = document.createElement("textarea");
            textarea.value = url;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
            showCopiedFeedback();
        } catch (err) {
            console.error("Fallback copy failed:", err);
            alert("Unable to share. Please copy the URL manually.");
        }
    });

    function showCopiedFeedback() {
        const originalHTML = shareButton.innerHTML;
        shareButton.innerHTML = "✅ Copied!";
        setTimeout(() => {
            shareButton.innerHTML = originalHTML;
        }, 2000);
    }
});
