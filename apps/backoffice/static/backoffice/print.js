const printButton = document.getElementById("print-order-summary");
if (printButton) {
    printButton.hidden = false;
    printButton.addEventListener("click", () => window.print());
}
