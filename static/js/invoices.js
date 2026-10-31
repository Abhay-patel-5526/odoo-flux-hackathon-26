document.addEventListener("DOMContentLoaded", () => {
    const itemsContainer = document.getElementById("invoiceItems");
    const addItemButton = document.getElementById("addInvoiceItem");
    const discountInput = document.getElementById("discount_amount");

    const subtotalDisplay = document.getElementById("subtotalDisplay");
    const taxDisplay = document.getElementById("taxDisplay");
    const totalDisplay = document.getElementById("totalDisplay");

    if (!itemsContainer) return;

    const formatINR = (amount) => {
        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            minimumFractionDigits: 2
        }).format(amount);
    };

    const getNumber = (value) => {
        const number = Number.parseFloat(value);
        return Number.isFinite(number) ? number : 0;
    };

    function calculateTotals() {
        let subtotal = 0;
        let tax = 0;

        const rows = itemsContainer.querySelectorAll(".invoice-item-row");

        rows.forEach((row) => {
            const quantity = getNumber(row.querySelector(".item-quantity")?.value);
            const price = getNumber(row.querySelector(".item-price")?.value);
            const taxPercentage = getNumber(row.querySelector(".item-tax")?.value);

            const lineSubtotal = Math.max(0, quantity * price);
            const lineTax = lineSubtotal * Math.max(0, taxPercentage) / 100;

            subtotal += lineSubtotal;
            tax += lineTax;
        });

        const discount = Math.min(
            subtotal + tax,
            Math.max(0, getNumber(discountInput?.value))
        );

        const total = Math.max(0, subtotal + tax - discount);

        if (subtotalDisplay) subtotalDisplay.textContent = formatINR(subtotal);
        if (taxDisplay) taxDisplay.textContent = formatINR(tax);
        if (totalDisplay) totalDisplay.textContent = formatINR(total);
    }

    function updateProductFields(row) {
        const productSelect = row.querySelector(".item-product");
        const descriptionInput = row.querySelector('input[name="description[]"]');
        const priceInput = row.querySelector(".item-price");

        if (!productSelect || !priceInput) return;

        const selectedOption = productSelect.options[productSelect.selectedIndex];

        if (!productSelect.value) {
            calculateTotals();
            return;
        }

        const productPrice = selectedOption?.dataset.price;

        if (productPrice !== undefined && productPrice !== "") {
            priceInput.value = Number(productPrice).toFixed(2);
        }

        if (descriptionInput && selectedOption?.textContent.trim()) {
            descriptionInput.value = selectedOption.textContent.trim();
        }

        calculateTotals();
    }

    function addItemRow() {
        const firstRow = itemsContainer.querySelector(".invoice-item-row");

        if (!firstRow) return;

        const newRow = firstRow.cloneNode(true);

        const productSelect = newRow.querySelector(".item-product");
        const descriptionInput = newRow.querySelector('input[name="description[]"]');
        const quantityInput = newRow.querySelector(".item-quantity");
        const priceInput = newRow.querySelector(".item-price");
        const taxInput = newRow.querySelector(".item-tax");

        if (productSelect) productSelect.value = "";
        if (descriptionInput) descriptionInput.value = "";
        if (quantityInput) quantityInput.value = "1";
        if (priceInput) priceInput.value = "0.00";
        if (taxInput) taxInput.value = "0";

        itemsContainer.appendChild(newRow);
        calculateTotals();
    }

    itemsContainer.addEventListener("input", (event) => {
        if (
            event.target.matches(".item-quantity") ||
            event.target.matches(".item-price") ||
            event.target.matches(".item-tax")
        ) {
            calculateTotals();
        }
    });

    itemsContainer.addEventListener("change", (event) => {
        if (event.target.matches(".item-product")) {
            updateProductFields(event.target.closest(".invoice-item-row"));
        } else if (
            event.target.matches(".item-quantity") ||
            event.target.matches(".item-price") ||
            event.target.matches(".item-tax")
        ) {
            calculateTotals();
        }
    });

    itemsContainer.addEventListener("click", (event) => {
        const removeButton = event.target.closest(".remove-invoice-item");

        if (!removeButton) return;

        const rows = itemsContainer.querySelectorAll(".invoice-item-row");

        if (rows.length <= 1) {
            const row = rows[0];
            if (!row) return;

            row.querySelector(".item-product").value = "";
            row.querySelector('input[name="description[]"]').value = "";
            row.querySelector(".item-quantity").value = "1";
            row.querySelector(".item-price").value = "0.00";
            row.querySelector(".item-tax").value = "0";
        } else {
            removeButton.closest(".invoice-item-row").remove();
        }

        calculateTotals();
    });

    addItemButton?.addEventListener("click", addItemRow);
    discountInput?.addEventListener("input", calculateTotals);

    calculateTotals();
});