/**
 * CALE Shop Admin Panel JavaScript.
 *
 * مسؤول حاليًا عن فتح/إغلاق Sidebar على الشاشات الصغيرة.
 * سيتم توسيعه لاحقًا لإضافة التفاعلات الإدارية المطلوبة.
 */
document.addEventListener("DOMContentLoaded", () => {
    const printButton = document.querySelector("[data-print-order]");
    if (printButton) {
        printButton.addEventListener("click", () => window.print());
    }

    const toggle = document.getElementById("sidebarToggle");
    const sidebar = document.querySelector(".admin-sidebar");

    if (!toggle || !sidebar) {
        return;
    }

    toggle.addEventListener("click", () => {
        sidebar.classList.toggle("is-open");
    });
});
