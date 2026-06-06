from odoo import models, fields, api, _

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------
    
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.user.allowed_warehouse_ids:
            # If the user has specific allowed warehouses, filter by those
            domain = [('warehouse_id', 'in', self.env.user.allowed_warehouse_ids.ids)] + domain
        return super(StockPickingType, self)._search(domain, offset=offset, limit=limit, order=order)