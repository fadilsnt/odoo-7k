import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownGroup } from "@web/core/dropdown/dropdown_group";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";

import { Component } from "@odoo/owl";
import { imageUrl } from "@web/core/utils/urls";

const userMenuRegistry = registry.category("user_menuitems");
const systrayRegistry = registry.category("systray");

/* ================================
 * USER MENU COMPONENT
 * ================================ */
export class UserMenu extends Component {
    static template = "web.UserMenu";
    static components = { DropdownGroup, Dropdown, DropdownItem, CheckBox };
    static props = {};

    setup() {
        this.userName = user.name;
        this.dbName = session.db;
        this.userLogin = user.login;

        const { partnerId, writeDate } = user;
        this.source = imageUrl(
            "res.partner",
            partnerId,
            "avatar_128",
            { unique: writeDate }
        );
    }

    getElements() {
        return userMenuRegistry
            .getAll()
            .map((el) => el(this.env))
            .filter((el) => (el.show ? el.show() : true))
            .sort((a, b) => (a.sequence || 100) - (b.sequence || 100));
    }
}

/* ================================
 * OVERRIDE SYSTRAY
 * ================================ */

/* HAPUS USER MENU BAWAAN */
systrayRegistry.remove("web.user_menu");

/* TAMBAHKAN USER MENU CUSTOM */
systrayRegistry.add(
    "web.user_menu",
    { Component: UserMenu },
    { sequence: 0 }
);
