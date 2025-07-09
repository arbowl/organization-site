document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.reply-toggle').forEach(btn => {
        btn.addEventListener('click', e => {
            e.preventDefault();
            const id = btn.dataset.comment;
            document.getElementById(`reply-${id}`).style.display = 'block';
        });
    });
});

document.addEventListener('DOMContentLoaded', function(){
  new EasyMDE({ element: document.getElementById('content') });
});
