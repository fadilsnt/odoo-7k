/** @odoo-module **/

import { onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { setActivePivotController } from "./ai_pivot_registry";

function patchPivotController(PivotController) {
    if (PivotController.__aiPivotFilterPatched) {
        return; // avoid double-patching
    }
    PivotController.__aiPivotFilterPatched = true;
    patch(PivotController.prototype, {
        setup() {
            super.setup(...arguments);
            setActivePivotController(this);
            onWillUnmount(() => setActivePivotController(null));
        },
    });
}

function tryPatchNow() {
    const viewsRegistry = registry.category("views");
    if (viewsRegistry.contains("pivot")) {
        const pivotView = viewsRegistry.get("pivot");
        if (pivotView && pivotView.Controller) {
            patchPivotController(pivotView.Controller);
            return true;
        }
    }
    return false;
}

if (!tryPatchNow()) {
    const viewsRegistry = registry.category("views");
    const onUpdate = (ev) => {
        const key = ev && ev.detail && ev.detail.key;
        if (key === "pivot" && tryPatchNow()) {
            viewsRegistry.removeEventListener("UPDATE", onUpdate);
        }
    };
    viewsRegistry.addEventListener("UPDATE", onUpdate);
}
