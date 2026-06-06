from odoo import models, fields, api, _
from odoo.osv import expression

class StockMove(models.Model):
    _inherit = 'stock.move'


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

    product_uom_category_id = fields.Many2one(store=True)

    valued_quantity = fields.Float(
        string='Valued Quantity',
        help='The quantity of the product that is valued.',
        compute='_compute_valued_quantity',
        store=True,
    )

    average_quantity = fields.Float(
        string='Average Quantity',
        help='The average quantity of the product in stock.',
        compute='_compute_valued_quantity',
        store=True,
        aggregator='avg'
    )


    

    @api.depends('quantity','location_id.usage', 'location_dest_id.usage')
    def _compute_valued_quantity(self):
        in_domain = ["&", ("location_id.usage", "not in", ("internal", "transit")), ("location_dest_id.usage", "in", ("internal", "transit"))]
        out_domain = ["&", ("location_id.usage", "in", ("internal", "transit")), ("location_dest_id.usage", "not in", ("internal", "transit"))]
        for move in self.filtered_domain(in_domain):
            move.valued_quantity = move.quantity
            move.average_quantity = move.quantity 
        for move in self.filtered_domain(out_domain):
            move.valued_quantity = -move.quantity
            move.average_quantity = -move.quantity


    @api.depends('product_id.container_capacity', 'quantity')
    def _compute_container_quantity(self):
        for move in self:
            if move.product_id.container_capacity > 0:
                move.container_quantity = move.quantity / move.product_id.container_capacity
            else:
                move.container_quantity = 0.0

    def _search(self, domain, offset=0, limit=None, order=None):
        if (
            self.env.user.allowed_warehouse_ids
            and not self.env.is_superuser()
            and not self.env.context.get('bypass_allowed_warehouse')
        ):
            warehouse_domain = [
                ('picking_type_id.warehouse_id', 'in',
                self.env.user.allowed_warehouse_ids.ids)
            ]

            domain = expression.AND([
                warehouse_domain,
                domain
            ])

        return super()._search(domain, offset=offset, limit=limit, order=order)

    def _set_backdate(self, backdate):
        """
        set backdate for done stock moves and their conresponding done stock move lines
        """
        stock_moves = self.filtered(lambda x: x.state == 'done')
        for move in stock_moves:
            move.write({'date': backdate})

        move_line_ids = self.mapped('move_line_ids').filtered(lambda x: x.state == 'done')
        if move_line_ids:
            move_line_ids.write({'date': backdate})