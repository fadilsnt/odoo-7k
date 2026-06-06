import logging
from odoo import models

_logger = logging.getLogger(__name__)


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    def _get_action(self, action_xmlid):
        action = super()._get_action(action_xmlid)

        if self.env.user.has_group('hd_inventory_custom.group_picking_view_only'):
            _logger.info("VIEW ONLY PICKING ACTION: %s", action_xmlid)

            action['views'] = [
                (self.env.ref('hd_inventory_custom.vpicktree_custom_view_only').id, 'list'),
                (self.env.ref('hd_inventory_custom.view_picking_form_view_only').id, 'form'),
            ]

            action['context'] = {
                **action.get('context', {}),
                'create': False,
                'edit': False,
                'delete': False,
            }

        return action