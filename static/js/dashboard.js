
document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");
    const menuToggle = document.getElementById("menuToggle");

    if (!sidebar || !menuToggle) {
        return;
    }

    // Create an overlay for mobile navigation.
    const overlay = document.createElement("div");
    overlay.className = "sidebar-overlay";
    document.body.appendChild(overlay);

    function openSidebar() {
        sidebar.classList.add("open");
        overlay.classList.add("show");
    }

    function closeSidebar() {
        sidebar.classList.remove("open");
        overlay.classList.remove("show");
    }

    menuToggle.addEventListener("click", function () {
        if (sidebar.classList.contains("open")) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });

    overlay.addEventListener("click", closeSidebar);

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeSidebar();
        }
    });

    // Close the mobile sidebar after choosing a navigation link.
    sidebar.querySelectorAll(".nav-link").forEach(function (link) {
        link.addEventListener("click", function () {
            if (window.innerWidth <= 800) {
                closeSidebar();
            }
        });
    });

    // Close sidebar if the screen becomes desktop-sized.
    window.addEventListener("resize", function () {
        if (window.innerWidth > 800) {
            closeSidebar();
        }
    });
});
