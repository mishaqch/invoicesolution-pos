/*
 * Super-admin Tenant form: show the "FBR sandbox scenarios" fieldset ONLY when
 * the tenant uses the direct DI-API connection (which runs sandbox scenarios).
 * For IMS / SDC tenants (FBR Fiscalization service — no token, no scenarios)
 * the fieldset is hidden live as soon as the connection type is chosen, on both
 * the create and edit pages.
 *
 * Unfold renders fieldsets inside Alpine.js tabs with x-show="activeTab==...",
 * so Alpine reactively rewrites the fieldset's inline `display`. Setting
 * element.style.display here loses that fight. So we toggle a CSS CLASS
 * (.ivs-hide-scenarios, display:none !important) that Alpine's inline style
 * can't override.
 *
 * The server (get_fieldsets) also drops the fieldset for SAVED ims_sdc tenants;
 * this handles the create page + live dropdown changes.
 */
(function () {
  "use strict";

  function findScenarioFieldset() {
    var sets = document.querySelectorAll("fieldset");
    for (var i = 0; i < sets.length; i++) {
      var h = sets[i].querySelector("h2");
      if (h && /FBR sandbox scenarios/i.test(h.textContent || "")) {
        return sets[i];
      }
    }
    return null;
  }

  function apply() {
    var select = document.getElementById("id_fbr_connection_type");
    var fieldset = findScenarioFieldset();
    if (!select || !fieldset) return;
    var show = select.value === "di_api";
    fieldset.classList.toggle("ivs-hide-scenarios", !show);
  }

  function init() {
    var select = document.getElementById("id_fbr_connection_type");
    if (!select) return;
    select.addEventListener("change", apply);
    // Run now, and again shortly after (Alpine may re-render tabs on mount).
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
