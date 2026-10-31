document.addEventListener("DOMContentLoaded", () => {
    // =========================================
    // QUOTATION FORM
    // =========================================

    const quotationLines = document.getElementById("quotation-lines");
    const lineTemplate = document.getElementById("quotation-line-template");
    const addLineButton = document.getElementById("add-quotation-line");
    const addLineBottom = document.getElementById("add-quotation-line-bottom");

    const discountInput = document.getElementById("discount_amount");
    const subtotalDisplay = document.getElementById("quotation-subtotal");
    const taxDisplay = document.getElementById("quotation-tax");
    const totalDisplay = document.getElementById("quotation-total");

    const quotationForm = document.getElementById("quotation-form");

    function money(value) {
        return Number(value || 0).toFixed(2);
    }

    function addQuotationLine() {
        if (!quotationLines || !lineTemplate) return;

        const fragment = lineTemplate.content.cloneNode(true);
        quotationLines.appendChild(fragment);
        calculateQuotation();
    }

    function calculateQuotation() {
        if (!quotationLines) return;

        let subtotal = 0;
        let totalTax = 0;

        quotationLines.querySelectorAll(".quotation-line").forEach(row => {
            const quantity = Math.max(
                0,
                Number(row.querySelector(".line-quantity")?.value || 0)
            );

            const price = Math.max(
                0,
                Number(row.querySelector(".line-price")?.value || 0)
            );

            const taxPercentage = Math.max(
                0,
                Number(row.querySelector(".line-tax")?.value || 0)
            );

            const lineSubtotal = quantity * price;
            const lineTax = lineSubtotal * taxPercentage / 100;

            subtotal += lineSubtotal;
            totalTax += lineTax;

            const lineDisplay = row.querySelector(".line-subtotal");

            if (lineDisplay) {
                lineDisplay.textContent = money(lineSubtotal + lineTax);
            }
        });

        const discount = Math.max(
            0,
            Number(discountInput?.value || 0)
        );

        // Match backend calculation: discount reduces taxable amount.
        const appliedDiscount = Math.min(discount, subtotal);
        const taxableRatio = subtotal > 0
            ? (subtotal - appliedDiscount) / subtotal
            : 0;

        const adjustedTax = totalTax * taxableRatio;
        const grandTotal = subtotal - appliedDiscount + adjustedTax;

        if (subtotalDisplay) {
            subtotalDisplay.textContent = money(subtotal);
        }

        if (taxDisplay) {
            taxDisplay.textContent = money(adjustedTax);
        }

        if (totalDisplay) {
            totalDisplay.textContent = money(grandTotal);
        }
    }

    if (addLineButton) {
        addLineButton.addEventListener("click", addQuotationLine);
    }

    if (addLineBottom) {
        addLineBottom.addEventListener("click", addQuotationLine);
    }

    if (quotationLines) {
        quotationLines.addEventListener("input", event => {
            if (
                event.target.matches(
                    ".line-quantity, .line-price, .line-tax"
                )
            ) {
                calculateQuotation();
            }
        });

        quotationLines.addEventListener("change", event => {
            if (event.target.matches(".line-product")) {
                const selected = event.target.selectedOptions[0];
                const row = event.target.closest(".quotation-line");

                if (!row || !selected) return;

                const price = selected.dataset.price;
                const priceInput = row.querySelector(".line-price");
                const descriptionInput = row.querySelector(
                    'input[name="description[]"]'
                );

                if (selected.value && price !== undefined) {
                    priceInput.value = money(price);

                    if (descriptionInput && !descriptionInput.value.trim()) {
                        descriptionInput.value = selected.textContent.trim();
                    }
                }

                calculateQuotation();
            }
        });

        quotationLines.addEventListener("click", event => {
            const removeButton = event.target.closest(".remove-line-btn");

            if (!removeButton) return;

            const row = removeButton.closest(".quotation-line");

            if (row) {
                row.remove();
                calculateQuotation();
            }
        });
    }

    if (discountInput) {
        discountInput.addEventListener("input", calculateQuotation);
    }

    if (quotationForm) {
        quotationForm.addEventListener("submit", event => {
            if (!quotationForm.checkValidity()) {
                event.preventDefault();
                quotationForm.reportValidity();
                return;
            }

            const rows = quotationLines
                ? quotationLines.querySelectorAll(".quotation-line")
                : [];

            if (rows.length === 0) {
                event.preventDefault();
                alert("Add at least one product line.");
            }
        });

        calculateQuotation();
    }

    // =========================================
    // TEMPLATE FORM
    // =========================================

    const templateLines = document.getElementById("template-lines");
    const templateLineTemplate = document.getElementById(
        "template-line-template"
    );

    const addTemplateLineButton = document.getElementById(
        "add-template-line"
    );

    function addTemplateLine() {
        if (!templateLines || !templateLineTemplate) return;

        const fragment = templateLineTemplate.content.cloneNode(true);
        templateLines.appendChild(fragment);
    }

    if (addTemplateLineButton) {
        addTemplateLineButton.addEventListener(
            "click",
            addTemplateLine
        );
    }

    if (templateLines) {
        templateLines.addEventListener("click", event => {
            const removeButton = event.target.closest(".remove-line-btn");

            if (!removeButton) return;

            const row = removeButton.closest(".template-line");

            if (row) row.remove();
        });

        // Only show plans belonging to the selected product.
        templateLines.addEventListener("change", event => {
            if (!event.target.matches(".template-product")) return;

            const row = event.target.closest(".template-line");
            const planSelect = row?.querySelector(".template-plan");

            if (!planSelect) return;

            const productId = event.target.value;

            planSelect.value = "";

            Array.from(planSelect.options).forEach(option => {
                if (!option.value) {
                    option.hidden = false;
                    return;
                }

                option.hidden = option.dataset.productId !== productId;
            });
        });
    }

    // =========================================
    // CONFIRMATION AND DOUBLE-SUBMIT PROTECTION
    // =========================================

    document.querySelectorAll("form[data-confirm]").forEach(form => {
        form.addEventListener("submit", event => {
            const message = form.dataset.confirm;

            if (message && !window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("form").forEach(form => {
        form.addEventListener("submit", () => {
            if (form.dataset.confirm && !window.confirmed) {
                // Confirmation is handled by the listener above.
                // Do not disable the button here if the user cancels.
            }
        });
    });
});