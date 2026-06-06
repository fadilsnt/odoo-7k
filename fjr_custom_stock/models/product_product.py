from odoo import models, fields, api, _

class ProductProduct(models.Model):
    _inherit = 'product.product'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------
    
    def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
        if self.env.user.allowed_warehouse_ids and not self._context.get('warehouse_id'):
            self = self.with_context(warehouse_id=self.env.user.allowed_warehouse_ids.ids)
        return super(ProductProduct, self)._compute_quantities_dict(lot_id, owner_id, package_id, from_date=from_date, to_date=to_date)