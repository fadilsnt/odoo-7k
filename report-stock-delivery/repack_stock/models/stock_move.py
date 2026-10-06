from odoo import models, fields


class StockMove(models.Model):
    _inherit = "stock.move"

    repack_line_id = fields.Many2one(
        "stock.repack.line",
        string="Repack Line",
        ondelete="set null",
        copy=False,
        index="btree_not_null",
    )
    repack_output_id = fields.Many2one(
        "stock.repack.output",
        string="Repack Output",
        ondelete="set null",
        copy=False,
        index="btree_not_null",
    )

    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        return distinct_fields + ["repack_line_id", "repack_output_id"]

    def _repack_cleanup_move(self):
        for move in self:
            if not move.exists():
                continue
            if move.state == 'done':
                continue
            if move.state != 'draft':
                move.sudo()._action_cancel()
            move.sudo().unlink()
