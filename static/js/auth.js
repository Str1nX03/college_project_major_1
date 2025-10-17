document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('.auth-form');
    const submitBtn = document.querySelector('.btn-submit');
    const inputs = document.querySelectorAll('.form-input');

    inputs.forEach(input => {
        input.addEventListener('focus', (e) => {
            const formGroup = e.target.closest('.form-group');
            const glow = formGroup.querySelector('.input-glow');
            if (glow) {
                glow.style.opacity = '1';
            }
        });

        input.addEventListener('blur', (e) => {
            const formGroup = e.target.closest('.form-group');
            const glow = formGroup.querySelector('.input-glow');
            if (glow) {
                glow.style.opacity = '0';
            }
        });

        input.addEventListener('input', (e) => {
            if (e.target.value.length > 0) {
                e.target.style.borderColor = 'var(--color-blue-primary)';
            } else {
                e.target.style.borderColor = 'var(--color-border)';
            }
        });
    });

    if (form) {
        form.addEventListener('submit', (e) => {
            submitBtn.classList.add('loading');
            submitBtn.disabled = true;
        });
    }

    const errorMessage = document.querySelector('.error-message');
    if (errorMessage) {
        setTimeout(() => {
            errorMessage.style.animation = 'fadeOut 0.5s ease-out forwards';
            setTimeout(() => {
                errorMessage.remove();
            }, 500);
        }, 5000);
    }
});