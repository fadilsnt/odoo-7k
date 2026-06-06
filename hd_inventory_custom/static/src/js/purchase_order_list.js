/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useState } from "@odoo/owl";

// -------------------------
// List Controller
// -------------------------
export class PurchaseOrderListController extends ListController {
    setup() {
        super.setup();
        this.state = useState({
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    }

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    }

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    }
};

PurchaseOrderListController.components = {
    ...ListController.components,
};

// -------------------------
// Kanban Controller
// -------------------------
export class PurchaseOrderKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.state = useState({
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    }

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    }

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    }
};

PurchaseOrderKanbanController.components = {
    ...KanbanController.components,
};

// -------------------------
// Register Views
// -------------------------
export const PurchaseOrderListView = {
    ...listView,
    Controller: PurchaseOrderListController,
};

export const PurchaseOrderKanbanView = {
    ...kanbanView,
    Controller: PurchaseOrderKanbanController,
};

registry.category("views").add("purchase_order_search_list", PurchaseOrderListView);
registry.category("views").add("purchase_order_search_kanban", PurchaseOrderKanbanView);