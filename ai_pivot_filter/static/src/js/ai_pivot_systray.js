/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { AiPivotDialog } from "./ai_pivot_dialog";

export class AiPivotSystray extends Component {
    static template = "ai_pivot_filter.AiPivotSystray";
    static props = {};

    setup() {
        this.dialog = useService("dialog");
        this.action = useService("action");

        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.render());
    }

    get isVisible() {
        const controller = this.action.currentController;
        return Boolean(
            controller &&
            controller.view &&
            controller.view.type === "pivot"
        );
    }

    openDialog() {
        this.dialog.add(AiPivotDialog);
    }
}

export const aiPivotSystrayItem = {
    Component: AiPivotSystray,
};

registry.category("systray").add("ai_pivot_filter.systray", aiPivotSystrayItem, { sequence: 1 });