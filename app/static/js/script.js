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