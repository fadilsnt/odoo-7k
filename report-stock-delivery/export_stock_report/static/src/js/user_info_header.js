/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

patch(UserMenu.prototype, {
    setup() {
        super.setup();
        this.auth = useService("auth");

        this.loadLogin();
    },

    async loadLogin() {
        const userId = this.auth.userId;

        if (!userId) {
            console.warn("User ID tidak ditemukan!");
            return;
        }

        // ambil login user
        const [rec] = await rpc("/web/dataset/call_kw/res.users/read", {
            model: "res.users",
            method: "read",
            args: [[userId], ["login"]],
            kwargs: {},
        });

        const login = rec?.login;

        if (login) {
            // ganti nama tampilannya
            this.user.name = login;

            // ganti db.name
            if (this.user.db) {
                this.user.db.name = login;
            }

            this.render(true); // refresh UI
        }
    },
});
