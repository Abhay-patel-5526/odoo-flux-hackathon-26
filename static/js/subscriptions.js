document.addEventListener("DOMContentLoaded", () => {

    // Prevent accidental double form submission.
    document.querySelectorAll("form").forEach((form) => {

        form.addEventListener("submit", (event) => {

            // Allow browser validation to run.
            if (!form.checkValidity()) {
                return;
            }

            // Confirmation for important actions.
            const confirmation = form.dataset.confirm;

            if (confirmation && !window.confirm(confirmation)) {
                event.preventDefault();
                return;
            }

            // Prevent duplicate submissions.
            const submitButton = form.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (submitButton) {
                submitButton.disabled = true;

                if (submitButton.tagName === "BUTTON") {
                    submitButton.textContent = "Please wait...";
                } else {
                    submitButton.value = "Please wait...";
                }
            }
        });
    });

    // Plan selection helper.
    const planSelect = document.getElementById("plan_id");

    if (planSelect) {
        planSelect.addEventListener("change", () => {
            const selectedOption = planSelect.options[planSelect.selectedIndex];

            if (!selectedOption || !selectedOption.value) {
                return;
            }

            // The backend remains responsible for validating plan availability.
            console.log("Selected plan ID:", selectedOption.value);
        });
    }

});