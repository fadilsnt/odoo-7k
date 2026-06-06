from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.returns('self')
    def _filter_visible_menus(self):
        menus = super()._filter_visible_menus()
        user = self.env.user

        if user.has_group('hd_inventory_custom.group_picking_view_only'):
            hide_menu_ids = [
                self.env.ref(x, raise_if_not_found=False).id
                for x in (
                    'stock.in_picking',
                    'stock.out_picking',
                    'stock.int_picking',
                )
                if self.env.ref(x, raise_if_not_found=False)
            ]

            if hide_menu_ids:
                menus = menus.filtered(lambda m: m.id not in hide_menu_ids)

        return menus