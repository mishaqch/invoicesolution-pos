/*
 * Super-admin Tenant form: hide the "Vertical" field when business mode is
 * "Digital Invoicing only". Vertical (grocery / pharmacy / restaurant) shapes
 * the POS counter/terminal experience — a back-office Digital Invoicing tenant
 * has no till, so the field is meaningless to them.
 *
 * The server also normalises vertical to the neutral default on save for DI
 * tenants (TenantAdminForm.save); this just keeps the form clean live, on both
 * the create page and when the business-mode dropdown changes.
 *
 * Unfold may render fields inside Alpine tabs that reactively rewrite inline
 * display, so (like fbr_connection_toggle) we toggle a CSS CLASS with
 * !important rather than element.style.display.
 */
(function () {
  "use strict";

  function findVerticalRow() {
    var sel = document.getElementById("id_vertical");
    if (!sel) return null;
    // Walk up to the field's row container (Django: .form-row / .field-vertical;
    // Unfold wraps differently) so the whole label+control hides together.
    var node = sel;
    for (var i = 0; i < 6 && node; i++) {
      node = node.parentElement;
      if (
        node &&
        (node.classList.contains("form-row") ||
          node.classList.contains("field-vertical") ||
          (node.getAttribute && /(^|\s)field-vertical(\s|$)/.test(node.getAttribute("class") || "")))
      ) {
        return node;
      }
    }
    // Fallback: hide the control's immediate wrapper.
    return sel.closest ? sel.closest("div") : sel.parentElement;
  }

  function apply() {
    var mode = document.getElementById("id_business_mode");
    var row = findVerticalRow();
    if (!mode || !row) return;
    var hide = mode.value === "digital_invoicing";
    row.classList.toggle("ivs-hide-vertical", hide);
  }

  function init() {
    var mode = document.getElementById("id_business_mode");
    if (!mode) return;
    mode.addEventListener("change", apply);
    apply();
    setTimeout(apply, 150);
    setTimeout(apply, 600);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
