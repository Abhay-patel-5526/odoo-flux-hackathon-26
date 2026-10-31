
document.addEventListener("DOMContentLoaded", function () {

    // ---------------------------------
    // Dynamic product variants
    // ---------------------------------

    const addVariantButton = document.getElementById("addVariant");
    const variantContainer = document.getElementById("variantContainer");

    if (addVariantButton && variantContainer) {

        addVariantButton.addEventListener("click", function () {

            const row = document.createElement("div");
            row.className = "variant-row new-variant";

            row.innerHTML = `
                <div class="form-group">
                    <label>Variant name</label>
                    <input
                        type="text"
                        name="new_variant_name"
                        class="product-input"
                        placeholder="e.g. Odoo Brand"
                    >
                </div>

                <div class="form-group">
                    <label>Additional price (₹)</label>
                    <input
                        type="number"
                        name="new_variant_price"
                        class="product-input"
                        min="0"
                        step="0.01"
                        value="0"
                    >
                </div>

                <button
                    type="button"
                    class="variant-remove"
                    aria-label="Remove variant"
                    title="Remove variant"
                >
                    ×
                </button>
            `;

            variantContainer.appendChild(row);
        });

        variantContainer.addEventListener("click", function (event) {

            const removeButton = event.target.closest(".variant-remove");

            if (!removeButton) {
                return;
            }

            const row = removeButton.closest(".variant-row");

            // Only remove newly added variants.
            // Existing variants are deactivated using their checkbox.
            if (row && row.classList.contains("new-variant")) {
                row.remove();
            }
        });
    }


    // ---------------------------------
    // Archive / restore confirmation
    // ---------------------------------

    document.querySelectorAll("[data-confirm]").forEach(function (form) {

        form.addEventListener("submit", function (event) {

            const message = form.dataset.confirm;

            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });


    // ---------------------------------
    // Prevent duplicate form submission
    // ---------------------------------

    document.querySelectorAll("[data-product-form]").forEach(function (form) {

        form.addEventListener("submit", function () {

            const submitButton = form.querySelector(
                'button[type="submit"]'
            );

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "Saving...";
            }
        });
    });

});
