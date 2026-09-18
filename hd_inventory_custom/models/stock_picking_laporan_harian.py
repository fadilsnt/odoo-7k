# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPickingLaporanHarian(models.Model):
    _name = 'stock.picking.laporan.harian'
    _description = 'Data Laporan Harian Picking'
    _order = 'sequence asc, id asc'

    picking_id = fields.Many2one(
        'stock.picking', string="Picking", required=True,
        ondelete='cascade', index=True)
    picking_state = fields.Selection(
        related='picking_id.state', string="Picking State", store=False)

    sequence = fields.Integer(string="No.", default=1, copy=False)
    kode = fields.Char(string="Kode", copy=False, readonly=True)

    location_dest_id = fields.Many2one('stock.location', string="To")

    oven_number = fields.Char(string="Nomor Oven")
    production_date = fields.Date(string="Tanggal Briket")
    line_packing = fields.Char(string="Line")
    camp_tgl_briket = fields.Char(string="Campuran")
    briket_tgu = fields.Char(string="Briket TGU (Jam)")
    shift_briket = fields.Char(string="Shift Briket/PA")
    bkr = fields.Char(string="BKR (HR/Jam/Kroak)")
    pembakar_penutup = fields.Char(string="Pembakar / Penutup")
    asumsi_berat_ikat = fields.Char(string="Asumsi Berat @Ikat")
    lubang_setom = fields.Char(string="Lubang Setom")
    bongkaran = fields.Char(string="Bongkaran")

    move_line_ids = fields.One2many(
        'stock.move.line', 'laporan_harian_id', string="Product Lines")
    consume_line_ids = fields.One2many(
        'stock.picking.laporan.harian.consume', 'laporan_harian_id',
        string="Consume Snapshot")

    product_count = fields.Integer(
        string="Jumlah Produk", compute="_compute_product_count")

    @api.depends('move_line_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.move_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('kode') and vals.get('picking_id'):
                picking = self.env['stock.picking'].browse(vals['picking_id'])
                seq = self.search_count([('picking_id', '=', picking.id)]) + 1
                vals['sequence'] = seq
                oven = (vals.get('oven_number') or '').strip()
                vals['kode'] = (
                    f"{picking.name}/{seq:03d}/{oven}" if oven
                    else f"{picking.name}/{seq:03d}"
                )
        return super().create(vals_list)

    def _check_editable(self):
        for rec in self:
            if rec.picking_id.state == 'done':
                raise UserError(_(
                    "Laporan Harian pada Picking yang sudah Selesai tidak dapat diubah/dihapus."
                ))

    def action_open_edit(self):
        self.ensure_one()
        self._check_editable()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Edit Laporan Harian'),
            'res_model': 'wizard.buat.laporan.harian.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.picking_id.id,
                'default_location_dest_id': self.location_dest_id.id,
                'default_laporan_harian_id': self.id,
            },
        }

    def action_open_view(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lihat Laporan Harian'),
            'res_model': 'wizard.buat.laporan.harian.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.picking_id.id,
                'default_location_dest_id': self.location_dest_id.id,
                'default_laporan_harian_id': self.id,
                'laporan_harian_readonly': True,
            },
        }

    def _rollback_contribution(self):
        for rec in self:
            moves = rec.move_line_ids.mapped('move_id')
            rec.move_line_ids.sudo().unlink()

            # Sinkronkan ulang qty Move yang terpengaruh (mengikuti logika wizard)
            for move in moves:
                if move.exists():
                    total_qty = sum(
                        move.move_line_ids.filtered(
                            lambda ml: ml.from_wizard
                        ).mapped('quantity')
                    )
                    move.sudo().with_context(
                        bypass_reservation_update=True,
                        bypass_move_line_create=True,
                    ).write({'product_uom_qty': total_qty})

            # Rollback kontribusi Consume Move yang dibuat oleh batch ini
            for consume in rec.consume_line_ids:
                consume_move = rec.picking_id.consume_move_ids.filtered(
                    lambda m: m.product_id.id == consume.product_id.id
                )
                if consume_move:
                    new_qty = max(consume_move.product_uom_qty - consume.qty, 0.0)
                    consume_move.sudo().write({
                        'product_uom_qty': new_qty,
                        'quantity': new_qty,
                    })

            rec.consume_line_ids.sudo().unlink()

    def action_delete(self):
        self.ensure_one()
        self._check_editable()

        self._rollback_contribution()
        self.sudo().unlink()

        return {'type': 'ir.actions.client', 'tag': 'reload'}


class StockPickingLaporanHarianConsume(models.Model):
    _name = 'stock.picking.laporan.harian.consume'
    _description = 'Snapshot Consume per Laporan Harian'

    laporan_harian_id = fields.Many2one(
        'stock.picking.laporan.harian', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", required=True)
    qty = fields.Float(string="Qty")
    product_uom_id = fields.Many2one('uom.uom', string="Unit of Measure")
