from odoo import models, fields, api, _
from odoo.osv import expression

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    container_quantity = fields.Float(
        string='Container Quantity',
        help='The quantity of the product in the container.',
        compute='_compute_container_quantity',
        store=True,
    )

    product_grade_id = fields.Many2one(
        'product.grade', string='Product Grade',
        help='The grade of the product, used for quality classification.',
        related='product_id.product_grade_id',
    )

    @api.depends('product_id.container_capacity', 'quantity')
    def _compute_container_quantity(self):
        for line in self:
            if line.product_id.container_capacity > 0:
                line.container_quantity = line.quantity / line.product_id.container_capacity
            else:
                line.container_quantity = 0.0

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.user.allowed_warehouse_ids:
            # If the user has specific allowed warehouses, filter by those
            domain = [('picking_type_id.warehouse_id', 'in', self.env.user.allowed_warehouse_ids.ids)] + domain
        return super(StockMoveLine, self)._search(domain, offset=offset, limit=limit, order=order)
        