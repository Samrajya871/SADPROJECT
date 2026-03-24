// Image preview
function previewImage(input) {
    const preview = document.getElementById('img-preview');
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const maxSize = 5 * 1024 * 1024; // 5MB

        // Check file size
        if (file.size > maxSize) {
            alert(`File is too large! Maximum size is 5MB. Your file is ${(file.size / 1024 / 1024).toFixed(2)}MB.`);
            input.value = ''; // Clear the input
            preview.style.display = 'none';
            return;
        }

        // Check file type
        const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            alert(`Invalid file type! Allowed: PNG, JPG, JPEG, GIF, WEBP`);
            input.value = ''; // Clear the input
            preview.style.display = 'none';
            return;
        }

        const reader = new FileReader();
        reader.onload = e => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.onerror = () => {
            alert('Error reading file. Please try again.');
            input.value = '';
            preview.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
}

// Drag & drop styling and file handling
document.addEventListener('DOMContentLoaded', () => {
    const zone = document.getElementById('drop-zone');
    const input = zone ? zone.querySelector('input[type=file]') : null;

    if (!zone || !input) return;

    // Make the entire drop zone clickable
    zone.addEventListener('click', () => {
        input.click();
    });

    // Drag over styling
    ['dragenter', 'dragover'].forEach(ev =>
        zone.addEventListener(ev, e => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        }, false)
    );

    // Drag leave and drop
    ['dragleave', 'drop'].forEach(ev =>
        zone.addEventListener(ev, e => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        }, false)
    );

    // Handle drop
    zone.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            // Set the files to the input
            input.files = files;
            // Trigger the onchange event
            const event = new Event('change', { bubbles: true });
            input.dispatchEvent(event);
            // Also preview
            previewImage(input);
        }
    }, false);
});