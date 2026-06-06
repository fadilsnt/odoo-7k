from odoo import models, fields, api, _

class ProductGrade(models.Model):
    _name = 'product.grade'
    _description = 'Product Grade'

    name = fields.Char(
        string='Grade Name',
        required=True,
        help='The name of the product grade.'
    )

    

    