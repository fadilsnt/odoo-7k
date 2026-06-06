from odoo import api, fields, models, _

class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    weight_per_product_attribute = fields.Float(string="Weight", default=1.0)
