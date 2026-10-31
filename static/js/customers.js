document.addEventListener("DOMContentLoaded", function () {

    // Confirmation before customer status changes
    document.querySelectorAll("[data-confirm]").forEach(function (form) {

        form.addEventListener("submit", function (event) {

            const message = form.dataset.confirm;

            if (!window.confirm(message)) {
                event.preventDefault();
            }

        });

    });

    // Prevent accidental double submission
    document.querySelectorAll("form").forEach(function (form) {

        form.addEventListener("submit", function () {

            if (!form.checkValidity()) {
                return;
            }

            const button = form.querySelector('button[type="submit"]');

            if (button && !button.disabled) {
                button.disabled = true;
                button.textContent = "Please wait...";
            }

        });

    });

});