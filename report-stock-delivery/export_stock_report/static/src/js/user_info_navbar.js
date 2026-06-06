/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

patch(UserMenu.prototype, {
    setup() {
        this._super?.(...arguments);
        this.user = this.env.services.user;
    },

    get userDisplayName() {
        const name = this.user?.name || "";
        const email = this.user?.email || "";
        return email ? `${name} | ${email}` : name;
    },
});
