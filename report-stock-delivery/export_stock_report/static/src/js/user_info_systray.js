/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SystrayMenu } from "@web/webclient/navbar/systray_menu";
import { registry } from "@web/core/registry";
import { Component, useService } from "@odoo/owl";

class UserInfoSystray extends Component {
    setup() {
        this.user = useService("user");
    }
}

UserInfoSystray.template = "export_stock_report.UserInfoSystray";

// Tambahkan ke systray menu
registry.category("systray").add("UserInfoSystray", { Component: UserInfoSystray }, { sequence: 1 });
