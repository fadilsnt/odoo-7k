from odoo import models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    repack_line_ids = fields.One2many(
        "stock.repack.line",
        "picking_id",
        string="Repack Lines",
    )

    is_repack_done = fields.Boolean(default=False)

    def button_validate(self):
        for picking in self:
            if picking.repack_line_ids:
                picking.is_repack_done = True

        return super().button_validate()

    def action_repack_resync(self):
        for picking in self:
            picking.repack_line_ids._sync_move_a()
            picking.repack_line_ids.mapped('repack_output_ids')._sync_move_b()
