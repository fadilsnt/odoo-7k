from odoo import models, fields, api, _

class UoM(models.Model):
    _inherit = 'uom.uom'

    weight_per_uom_category = fields.Float(string="Weight", default=1.0)