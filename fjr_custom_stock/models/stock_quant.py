from odoo import models, fields, api, _

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    product_grade_id = fields.Many2one(
        'product.grade', string='Product Grade',
        help='The grade of the product, used for quality classification.',
        related='product_id.product_grade_id',
    )

    container_quantity = fields.Float(
        string='Container Quantity',
        help='The quantity of the container in which the product is stored.',
        digits='Product Unit of Measure',
        compute='_compute_container_quantity',
        store=True,
    )

    uom_category_id = fields.Many2one(
        'uom.category', string='UoM Category',
        related='product_id.uom_id.category_id',
        store=True,
        help='The unit of measure category for the product.',
    )

    sales_person_ids = fields.Many2many(
        related='product_id.sales_person_ids', 
    )

    @api.depends('product_id.container_capacity', 'quantity')
    def _compute_container_quantity(self):
        for move in self:
            if move.product_id.container_capacity > 0:
                move.container_quantity = move.quantity / move.product_id.container_capacity
            else:
                move.container_quantity = 0.0

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.user.allowed_warehouse_ids:
            # If the user has specific allowed warehouses, filter by those
            domain = [('warehouse_id', 'in', self.env.user.allowed_warehouse_ids.ids)] + domain
        return super(StockQuant, self)._search(domain, offset=offset, limit=limit, order=order)