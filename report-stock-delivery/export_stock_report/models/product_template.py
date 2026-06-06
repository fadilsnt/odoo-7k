from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qty_available_stored = fields.Float(
        string="Qty On Hand (Stored)",
        compute="_compute_qty_available_stored",
        store=True,
    )
    virtual_available_stored = fields.Float(
        string="Forecasted (Stored)",
        compute="_compute_virtual_available_stored",
        store=True,
    )

    @api.depends('qty_available')
    def _compute_qty_available_stored(self):
        for rec in self:
            rec.qty_available_stored = rec.qty_available

    @api.depends('virtual_available')
    def _compute_virtual_available_stored(self):
        for rec in self:
            rec.virtual_available_stored = rec.virtual_available
