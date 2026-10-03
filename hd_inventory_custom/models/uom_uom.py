from odoo import models, fields, api, _

class UoM(models.Model):
    _inherit = 'uom.uom'

    weight_per_uom_category = fields.Float(string="Weight", default=1.0)

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            recs = self.search(['|',('name',operator, name),('weight_per_uom_category',operator, name)] + args, limit=limit)
        else:
            recs = self.search([] + args, limit=limit)
        return recs.name_get()

    def name_get(self):
        result = []
        for rec in self :
            result.append((rec.id, "%s (%s)" % (rec.name, rec.weight_per_uom_category)))
        return result