document.addEventListener("DOMContentLoaded", () => {
    // Prevent repeated invoice filter submissions.
    const filterForms = document.querySelectorAll(".portal-filter-form");

    filterForms.forEach((form) => {
        form.addEventListener("submit", () => {
            const submitButton = form.querySelector(
                'button[type="submit"]'
            );

            if (!submitButton) return;

            submitButton.disabled = true;
            submitButton.textContent = "Filtering...";
        });
    });

    // Print invoice when a print button is clicked.
    const printButtons = document.querySelectorAll("[data-print-invoice]");

    printButtons.forEach((button) => {
        button.addEventListener("click", () => {
            window.print();
        });
    });
});