from odoo import models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    repack_line_ids = fields.One2many(
        "stock.repack.line",
        "picking_id",
        string="Repack Lines",
    )

    is_repack_done = fields.Boolean(default=False, copy=False)

    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            if picking.state == 'done' and picking.repack_line_ids:
                picking.is_repack_done = True
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'location_id' in vals or 'location_dest_id' in vals:
            self.filtered('repack_line_ids').action_repack_resync()
        return res

    def action_repack_resync(self):
        for picking in self.filtered(lambda p: p.state not in ('done', 'cancel')):
            lines = picking.repack_line_ids
            lines._sync_move_a()
            lines.mapped('repack_output_ids')._sync_move_b()
        return True
