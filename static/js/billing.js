document.addEventListener("DOMContentLoaded", () => {
    const generateForm = document.querySelector(
        'form[action*="generate_invoices"]'
    );

    if (!generateForm) return;

    generateForm.addEventListener("submit", () => {
        const submitButton = generateForm.querySelector(
            'button[type="submit"]'
        );

        if (!submitButton) return;

        submitButton.disabled = true;
        submitButton.textContent = "Generating invoices...";

        submitButton.classList.add("is-loading");
    });
});