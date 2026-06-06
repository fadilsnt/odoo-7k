from odoo import models, fields, api, _
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    actual_date = fields.Datetime(
        string='Actual Date',
        help='The actual date when the picking was processed.',)
    

    def _action_done(self):
        res = super(StockPicking, self)._action_done()
        pickings_with_actual_date = self.filtered(lambda p: p.actual_date)

        for picking in pickings_with_actual_date:
            picking.move_ids._set_backdate(picking.actual_date)
            picking.write({'date_done': picking.actual_date})

        picking_without_actual_date = self - pickings_with_actual_date
        if picking_without_actual_date:
            picking_without_actual_date.write({'actual_date': fields.Datetime.now()})

        return res
        
        