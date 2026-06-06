/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { DateSearch } from "./purchase_date_search";
import { patch } from "@web/core/utils/patch";
import { PurchaseOrderListController } from "./purchase_order_list";
import { PurchaseOrderKanbanController } from "./purchase_order_list";
import { useState } from "@odoo/owl";

console.log("inside the header select.js");

// -------------------------
// ListController
// -------------------------
patch(ListController.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            purchase_order_search: false,
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    },

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    },

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    },
});

// -------------------------
// PurchaseOrderListController
// -------------------------
patch(PurchaseOrderListController.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            purchase_order_search: true,
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    },

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    },

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    },
});

// -------------------------
// KanbanController
// -------------------------
patch(KanbanController.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            purchase_order_search: false,
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    },

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    },

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    },
});

// -------------------------
// PurchaseOrderKanbanController
// -------------------------
patch(PurchaseOrderKanbanController.prototype, {
    setup() {
        super.setup();
        this.state = useState({
            purchase_order_search: true,
            warehouseId: false,
            warehouses: [],
        });
        this.loadWarehouses();
    },

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    },

    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    },
});

// -------------------------
// Inject DateSearch component
// -------------------------
patch(PurchaseOrderListController.components, Object.assign({}, ListController.components, { DateSearch }));
patch(PurchaseOrderKanbanController.components, Object.assign({}, KanbanController.components, { DateSearch }));