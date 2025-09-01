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
                    console.error("Comment clipboard API failed:", err);
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
                console.error("Comment fallback copy failed:", err);
                alert("Unable to share comment. Please copy the URL manually.");
            }
        });
    });

    // Active Discussions collapsible section
    const discussionsToggle = document.getElementById('discussions-toggle');
    const discussionsContent = document.getElementById('discussions-content');
    const discussionsToggleIcon = document.getElementById('discussions-toggle-icon');
    
    if (discussionsToggle && discussionsContent && discussionsToggleIcon) {
        // Check if user has a saved preference, default to collapsed if no preference
        const isCollapsed = localStorage.getItem('discussions-collapsed') !== 'false'; // Default to true (collapsed)
        
        // Set initial state
        if (isCollapsed) {
            discussionsContent.style.maxHeight = '0px';
            discussionsContent.style.opacity = '0';
            discussionsToggleIcon.style.transform = 'rotate(-90deg)';
        } else {
            discussionsContent.style.maxHeight = discussionsContent.scrollHeight + 'px';
            discussionsContent.style.opacity = '1';
        }
        
        // Add click event listener
        discussionsToggle.addEventListener('click', () => {
            const isCurrentlyCollapsed = discussionsContent.style.maxHeight === '0px';
            
            if (isCurrentlyCollapsed) {
                // Expand
                discussionsContent.style.maxHeight = discussionsContent.scrollHeight + 'px';
                discussionsContent.style.opacity = '1';
                discussionsToggleIcon.style.transform = 'rotate(0deg)';
                localStorage.setItem('discussions-collapsed', 'false');
            } else {
                // Collapse
                discussionsContent.style.maxHeight = '0px';
                discussionsContent.style.opacity = '0';
                discussionsToggleIcon.style.transform = 'rotate(-90deg)';
                localStorage.setItem('discussions-collapsed', 'true');
            }
        });
        
        // Handle window resize to recalculate maxHeight
        window.addEventListener('resize', () => {
            if (discussionsContent.style.maxHeight !== '0px') {
                discussionsContent.style.maxHeight = discussionsContent.scrollHeight + 'px';
            }
        });
    }

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

class ArticleSpectrum extends HTMLElement {
    static get observedAttributes() { return ["roots", "branches"]; }


    connectedCallback() { this.render(); }
    attributeChangedCallback() { this.render(); }


    get roots() { return Number(this.getAttribute("roots")) || 0; }
    get branches() { return Number(this.getAttribute("branches")) || 0; }


    computePosition() {
        // Delta-driven mapping: a difference of 5 fully saturates the slider to either end
        const d = this.roots - this.branches; // positive => Applicable, negative => Foundational
        const clamped = Math.max(-3, Math.min(3, d));
        return 50 + (clamped / 3) * 50; // 0..100
    }


    render() {
        const r = this.roots, b = this.branches; const pos = Math.max(0, Math.min(100, this.computePosition()));
        const label = pos < 45 ? "Foundational" : (pos > 55 ? "Applicable" : "Transitional");
        const title = this.getAttribute("data-title") || "";


        this.innerHTML = `
        <div class="spectrum ${this.classList.contains('compact') ? 'compact' : ''}">
        <div class="label-row">
        <div class="side left">Premise</div>
        <div class="center">Commentary</div>
        <div class="side right">Application</div>
        </div>
        <div class="wrap">
        <div class="track" aria-hidden="true" style="height:12px"></div>
        <div class="thumb" style="left:${pos}%" role="img" aria-label="${label} – position ${Math.round(pos)} of 100"></div>
        <div class="badge" style="left:${pos}%">${label}${title ? ` · ${title}` : ''}</div>
        </div>
        </div>
        `;
    }
}


customElements.define('article-spectrum', ArticleSpectrum);