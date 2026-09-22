from odoo import api, models, fields, _
from odoo.exceptions import UserError

class StockRepackLine(models.Model):
    _name = "stock.repack.line"
    _description = "Stock Repack Line"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Picking",
        ondelete="cascade"
    )

    product_a_id = fields.Many2one(
        "product.product",
        string="Product Awal",
        required=True
    )

    qty_a = fields.Float(
        string="Qty",
        required=True
    )

    product_b_id = fields.Many2one(
        "product.product",
        string="Product Repack",
    )

    qty_b = fields.Float(
        string="Qty",
    )

    repack_output_ids = fields.One2many(
        "stock.repack.output",
        "repack_line_id",
        string="Hasil Repack"
    )

    move_a_id = fields.Many2one(
        "stock.move",
        string="Produk Awal",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    move_a_state = fields.Selection(
        related="move_a_id.state",
        string="Status Produk Awal",
        readonly=True,
    )

    def _check_editable(self):
        for rec in self:
            picking = rec.picking_id
            if picking and picking.state == 'done':
                raise UserError(_(
                    "Tidak bisa mengubah/menghapus Repack Line karena "
                    "picking %s sudah Selesai (Done)."
                ) % picking.name)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_editable()
        if not self.env.context.get('repack_sync_skip'):
            records._sync_move_a()
        return records

    def write(self, vals):
        if not self.env.context.get('repack_sync_skip'):
            self._check_editable()
        res = super().write(vals)
        if not self.env.context.get('repack_sync_skip'):
            self._sync_move_a()
        return res

    def unlink(self):
        self._check_editable()
        self.mapped('repack_output_ids').unlink()

        moves = self.mapped('move_a_id').filtered(lambda m: m.exists())
        res = super().unlink()
        moves._repack_cleanup_move()
        return res

    def _sync_move_a(self):
        Move = self.env['stock.move'].sudo()

        for rec in self:
            picking = rec.picking_id
            move = rec.move_a_id

            if not picking or not rec.product_a_id or not rec.qty_a:
                if move and move.state not in ('done', 'cancel'):
                    move._repack_cleanup_move()
                    rec.with_context(repack_sync_skip=True).write({'move_a_id': False})
                continue

            vals = {
                'name': _("Repack - Produk Awal %s") % rec.product_a_id.display_name,
                'picking_id': picking.id,
                'product_id': rec.product_a_id.id,
                'product_uom': rec.product_a_id.uom_id.id,
                'product_uom_qty': rec.qty_a,
                'quantity': rec.qty_a,
                'location_id': picking.location_dest_id.id,
                'location_dest_id': picking.location_id.id,
                'company_id': picking.company_id.id,
                'repack_line_id': rec.id,
            }

            if move and move.state not in ('done', 'cancel'):
                move.write(vals)
            else:
                new_move = Move.create(vals)
                rec.with_context(repack_sync_skip=True).write({'move_a_id': new_move.id})


class StockRepackOutput(models.Model):
    _name = "stock.repack.output"
    _description = "Stock Repack Output"

    repack_line_id = fields.Many2one(
        "stock.repack.line",
        ondelete="cascade"
    )

    product_b_id = fields.Many2one(
        "product.product",
        string="Product Hasil",
        required=True
    )

    qty_b = fields.Float(
        string="Qty Hasil",
        required=True
    )

    move_b_id = fields.Many2one(
        "stock.move",
        string="Produk Hasil",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    move_b_state = fields.Selection(
        related="move_b_id.state",
        string="Status Produk Hasil",
        readonly=True,
    )

    def _check_editable(self):
        for rec in self:
            picking = rec.repack_line_id.picking_id
            if picking and picking.state == 'done':
                raise UserError(_(
                    "Tidak bisa mengubah/menghapus Hasil Repack karena "
                    "picking %s sudah Selesai (Done)."
                ) % picking.name)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_editable()
        if not self.env.context.get('repack_sync_skip'):
            records._sync_move_b()
        return records

    def write(self, vals):
        if not self.env.context.get('repack_sync_skip'):
            self._check_editable()
        res = super().write(vals)
        if not self.env.context.get('repack_sync_skip'):
            self._sync_move_b()
        return res

    def unlink(self):
        self._check_editable()
        moves = self.mapped('move_b_id').filtered(lambda m: m.exists())
        res = super().unlink()
        moves._repack_cleanup_move()
        return res

    def _sync_move_b(self):
        Move = self.env['stock.move'].sudo()

        for rec in self:
            line = rec.repack_line_id
            picking = line.picking_id if line else False
            move = rec.move_b_id

            if not picking or not rec.product_b_id or not rec.qty_b:
                if move and move.state not in ('done', 'cancel'):
                    move._repack_cleanup_move()
                    rec.with_context(repack_sync_skip=True).write({'move_b_id': False})
                continue

            vals = {
                'name': _("Repack - Produk Hasil %s") % rec.product_b_id.display_name,
                'picking_id': picking.id,
                'product_id': rec.product_b_id.id,
                'product_uom': rec.product_b_id.uom_id.id,
                'product_uom_qty': rec.qty_b,
                'quantity': rec.qty_b,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'company_id': picking.company_id.id,
                'repack_output_id': rec.id,
            }

            if move and move.state not in ('done', 'cancel'):
                move.write(vals)
            else:
                new_move = Move.create(vals)
                rec.with_context(repack_sync_skip=True).write({'move_b_id': new_move.id})
