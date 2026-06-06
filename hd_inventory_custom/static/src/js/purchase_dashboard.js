/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PurchaseDashBoard } from "@purchase/views/purchase_dashboard";
import { DateSearch } from "./purchase_date_search";
import { useState } from "@odoo/owl";

// pastikan components ada
PurchaseDashBoard.components ??= {};

patch(PurchaseDashBoard.components, {
    DateSearch,
});

patch(PurchaseDashBoard.prototype, {
    setup() {
        super.setup?.();
        this.purchase_order_search = true;

        // State warehouse
        this.state = useState({
            warehouseId: false,
            warehouses: [],
        });

        // Load warehouses dari ORM
        this.loadWarehouses();
    },

    async loadWarehouses() {
        this.state.warehouses = await this.orm.searchRead(
            "stock.warehouse",
            [],
            ["id", "name"]
        );
    },

    // Handler dropdown warehouse
    onWarehouseChanged(ev) {
        this.state.warehouseId = ev.target.value ? parseInt(ev.target.value) : false;
        if (this.applySearch) this.applySearch();
    },
});