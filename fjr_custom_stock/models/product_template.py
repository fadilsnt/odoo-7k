from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    container_capacity = fields.Float(
        string='Container Capacity',
        help='The capacity of the container in which the product is stored.',
        default=0.0,
        digits='Product Unit of Measure',
    )

    uom_sale_id = fields.Many2one(
        'uom.uom', 'Purchase Unit',
        compute='_compute_uom_sale_id', required=True, readonly=False, store=True, precompute=True,
        domain="[('category_id', '=', uom_category_id)]",
        help="Default unit of measure used for purchase orders. It must be in the same category as the default unit of measure.")


    product_grade_id = fields.Many2one(
        'product.grade', string='Product Grade',
        help='The grade of the product, used for quality classification.',
    )

    

    uom_category_id = fields.Many2one(store=True)

    sales_person_ids = fields.Many2many(
        'res.users', string='Sales Persons',
        help='Sales persons who are responsible for this product template.',
    )
    
    @api.depends('uom_id', 'uom_category_id')
    def _compute_uom_sale_id(self):
        for template in self:
            if not template.uom_po_id or template.uom_id.category_id != template.uom_po_id.category_id:
                template.uom_po_id = template.uom_id


    def _compute_quantities_dict(self):
        if self.env.user.allowed_warehouse_ids and not self._context.get('warehouse_id'):
            self = self.with_context(warehouse_id=self.env.user.allowed_warehouse_ids.ids)
        return super(ProductTemplate, self)._compute_quantities_dict()