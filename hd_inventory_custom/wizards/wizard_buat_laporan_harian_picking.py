from odoo import models, fields, api, _

class WizardBuatLaporanHarianPicking(models.TransientModel):
    _name = 'wizard.buat.laporan.harian.picking'
    _description = "Wizard Buat Laporan Harian Picking"

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    picking_type_code = fields.Selection(
        related='picking_id.picking_type_code',
        readonly=True)
    oven_number = fields.Char(string="Nomor Oven")
    production_date = fields.Date(string="Tanggal Produksi")
    product_line_ids = fields.One2many('wizard.buat.laporan.harian.picking.line', 'wizard_id', string="Product Lines")
    consume_line_ids = fields.One2many('wizard.buat.laporan.harian.consume.line', 'wizard_id', string="Consume")
    location_dest_id = fields.Many2one('stock.location', 'To', domain="[('usage', '!=', 'view')]", check_company=True, required=True, readonly=True)

    line_packing = fields.Char(string="Line")
    camp_tgl_briket = fields.Char(string="Camp/TGL Briket")
    briket_tgu = fields.Char(string="Briket TGU (Jam)")
    shift_briket = fields.Char(string="Shift Briket/PA")
    bkr = fields.Char(string="BKR (HR/Jam/Kroak)")
    pembakar_penutup = fields.Char(string="Pembakar / Penutup")
    asumsi_berat_ikat = fields.Char(string="Asumsi Berat @Ikat")

    lubang_setom = fields.Char(string="Lubang Setom")
    bongkaran = fields.Char(string="Bongkaran")

    def _sync_move_quantity(self, move):
        total_qty = sum(move.move_line_ids.filtered(lambda ml: ml.from_wizard).mapped('quantity'))
        total_tonase = sum(move.move_line_ids.filtered(lambda ml: ml.from_wizard).mapped('tonase_asli'))

        move.with_context(
            bypass_reservation_update=True,
            bypass_move_line_create=True,
        ).write({
            'product_uom_qty': total_qty,
            'tonase_asli': total_tonase
        })    

    def action_apply(self):
        self.ensure_one()
        return self.sudo().with_context(bypass_move_rule=True)._action_apply()

    def _action_apply(self):
        self = self.sudo()

        Move = self.env['stock.move'].sudo()
        MoveLine = self.env['stock.move.line'].sudo()
        moves = self.env['stock.move']

        for line in self.product_line_ids:
            move = self._get_or_create_move(line, Move)
            self._upsert_move_line(move, line, MoveLine)

            moves |= move

        for move in moves:
            self._sync_move_quantity(move)
        
        self._sync_picking_consume()

    def _get_or_create_move(self, line, Move):
        move = Move.search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', line.product_id.id),
            ('product_uom', '=', line.product_uom_id.id),
        ], limit=1)

        ctx = dict(self.env.context, bypass_move_line_create=True)

        if not move:
            move = Move.with_context(ctx).create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': 0,
                'product_uom': line.product_uom_id.id,
                'picking_id': self.picking_id.id,
                'location_id': self.picking_id.location_id.id,
                'location_dest_id': self.location_dest_id.id,
            })

        return move

    def _get_existing_move_line(self, move, line):
        return self.env['stock.move.line'].sudo().search([
            ('move_id', '=', move.id),
            ('product_id', '=', line.product_id.id),
            ('product_uom_id', '=', line.product_uom_id.id), 
        ])

    def _prepare_move_line_vals(self, move, line):
        wizard = self.sudo()
        move = move.sudo()

        return {
            'from_wizard': True,
            'picking_id': wizard.picking_id.id,
            'move_id': move.id,
            'product_id': line.product_id.id,
            'quantity': line.qty,
            'tonase_asli': line.tonase_asli,
            'product_uom_id': line.product_uom_id.id,
            'location_id': move.location_id.id,
            'location_dest_id': wizard.location_dest_id.id,
            'owner_id': move.owner_id.id,
            'oven_number': wizard.oven_number,
            'production_date': wizard.production_date,
            'line_packing': wizard.line_packing,
            'camp_tgl_briket': wizard.camp_tgl_briket,
            'briket_tgu': wizard.briket_tgu,
            'shift_briket': wizard.shift_briket,
            'bkr': wizard.bkr,
            'pembakar_penutup': wizard.pembakar_penutup,
            'asumsi_berat_ikat': wizard.asumsi_berat_ikat,
            'bongkaran': wizard.bongkaran,
            'lubang_setom': wizard.lubang_setom
        }

    def _upsert_move_line(self, move, line, MoveLine):
        wizard = self.sudo()

        candidate = MoveLine.search([
            ('move_id', '=', move.id),
            ('product_id', '=', line.product_id.id),
            ('product_uom_id', '=', line.product_uom_id.id),
            ('from_wizard', '=', True),
            ('oven_number', '=', wizard.oven_number or False),
            ('production_date', '=', wizard.production_date or False),
            ('line_packing', '=', wizard.line_packing or False),
            ('camp_tgl_briket', '=', wizard.camp_tgl_briket or False),
            ('briket_tgu', '=', wizard.briket_tgu or False),
            ('shift_briket', '=', wizard.shift_briket or False),
            ('bkr', '=', wizard.bkr or False),
            ('pembakar_penutup', '=', wizard.pembakar_penutup or False),
            ('asumsi_berat_ikat', '=', wizard.asumsi_berat_ikat or False),
            ('bongkaran', '=', wizard.bongkaran or False),
            ('lubang_setom', '=', wizard.lubang_setom or False),                        
        ], limit=1)

        if candidate:
            candidate.write({
                'quantity': candidate.quantity + line.qty,
                'tonase_asli': candidate.tonase_asli + line.tonase_asli
            })
        else:
            vals = self._prepare_move_line_vals(move, line)
            MoveLine.create(vals)
    
    def _sync_picking_consume(self):
        for line in self.consume_line_ids:
            if line.product_id.id not in self.picking_id.consume_line_ids.mapped('product_id').ids:
                self.picking_id.consume_line_ids.create({
                    'picking_id': self.picking_id.id,
                    'product_id': line.product_id.id,
                    'qty': line.qty,
                    'product_uom_id': line.product_uom_id.id,
                })
            else:
                for consume in self.picking_id.consume_line_ids.filtered(lambda l: l.product_id.id == line.product_id.id):
                    consume.write({
                        'qty': line.qty,
                        'product_uom_id': line.product_uom_id.id,
                    })
    
    def update_consume(self):
        self.ensure_one()

        for line in self.product_line_ids:
            if not line.product_id.consume_product_ids:
                continue
            
            for product in line.product_id.consume_product_ids:
                if product.id not in self.consume_line_ids.mapped('product_id').ids:
                    self.consume_line_ids.create({
                        'wizard_id': self.id,
                        'product_id': product.id,
                        'qty': line.qty,
                        'product_uom_id': product.uom_id.id,
                    })
                else:
                    for consume in self.consume_line_ids.filtered(lambda l: l.product_id.id == product.id):
                        consume.write({
                            'qty': line.qty,
                        })
        
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Laporan Harian Picking',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

class WizardBuatLaporanHarianPickingLine(models.TransientModel):
    _name = 'wizard.buat.laporan.harian.picking.line'
    _description = "Wizard Line"

    wizard_id = fields.Many2one('wizard.buat.laporan.harian.picking', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product")
    product_uom_category_id = fields.Many2one('uom.category', related='product_id.uom_id.category_id', store=False, readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', domain="[('category_id', '=', product_uom_category_id)]")

    qty = fields.Float(string="Qty")
    tonase_asli = fields.Float(string="Tonase Asli")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
        else:
            self.product_uom_id = False

class WizardBuatLaporanHarianConsumeLine(models.TransientModel):
    _name = 'wizard.buat.laporan.harian.consume.line'
    _description = "Wizard Consume Line"

    wizard_id = fields.Many2one('wizard.buat.laporan.harian.picking', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product")
    product_uom_category_id = fields.Many2one('uom.category', related='product_id.uom_id.category_id', store=False, readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', domain="[('category_id', '=', product_uom_category_id)]")
    qty = fields.Float(string="Qty")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
        else:
            self.product_uom_id = False