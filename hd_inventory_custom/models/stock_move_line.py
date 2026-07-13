from odoo import models, fields, api, _
from collections import OrderedDict, defaultdict
from odoo.exceptions import UserError, ValidationError
from odoo.tools import (float_compare, OrderedSet)

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

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
    tonase_asli = fields.Float(string="Tonase Asli", compute="_compute_tonase_asli", store=True)
    bongkaran = fields.Char(string="Bongkaran")    
    from_wizard = fields.Boolean(default=False)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True, domain="[('category_id', '=', product_uom_category_id)]", readonly=True)

    # =========================================================
    # PHYSICAL INVENTORY
    # =========================================================
    notes = fields.Text(string="Keterangan", related='move_id.notes', store=True)

    @api.depends('move_id', 'move_id.tonase_asli')
    def _compute_tonase_asli(self):
        for rec in self:
            rec.tonase_asli = rec.move_id.tonase_asli
            
    def _action_done(self):
        ml_ids_tracked_without_lot = OrderedSet()
        ml_ids_to_delete = OrderedSet()
        ml_ids_to_create_lot = OrderedSet()
        ml_ids_to_check = defaultdict(OrderedSet)

        for ml in self:
            uom_qty = ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id, round=False)
            precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            quantity = float(fields.Float.round(ml.quantity, precision_digits))
            if float_compare(uom_qty, quantity, precision_digits=precision_digits) != 0:
                raise UserError(_('The quantity done for the product "%(product)s" doesn\'t respect the rounding precision '
                                  'defined on the unit of measure "%(unit)s". Please change the quantity done or the '
                                  'rounding precision of your unit of measure.',
                                  product=ml.product_id.display_name, unit=ml.product_uom_id.name))

            qty_done_float_compared = float_compare(ml.quantity, 0, precision_rounding=ml.product_uom_id.rounding)
            if qty_done_float_compared > 0:
                if ml.product_id.tracking == 'none':
                    continue
                picking_type_id = ml.move_id.picking_type_id
                if not picking_type_id and not ml.is_inventory and not ml.lot_id:
                    ml_ids_tracked_without_lot.add(ml.id)
                    continue
                if not picking_type_id or ml.lot_id or (not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots):
                    continue
                if picking_type_id.use_create_lots:
                    ml_ids_to_check[(ml.product_id, ml.company_id)].add(ml.id)
                else:
                    ml_ids_tracked_without_lot.add(ml.id)

            elif qty_done_float_compared < 0:
                raise UserError(_('No negative quantities allowed'))
            elif not ml.is_inventory:
                ml_ids_to_delete.add(ml.id)

        for (product, company), mls in ml_ids_to_check.items():
            mls = self.env['stock.move.line'].browse(mls)
            lots = self.env['stock.lot'].search([
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
                ('product_id', '=', product.id),
                ('name', 'in', mls.mapped('lot_name')),
            ])
            lots = {lot.name: lot for lot in lots}
            for ml in mls:
                lot = lots.get(ml.lot_name)
                if lot:
                    ml.lot_id = lot.id
                elif ml.lot_name:
                    ml_ids_to_create_lot.add(ml.id)
                else:
                    ml_ids_tracked_without_lot.add(ml.id)

        if ml_ids_tracked_without_lot:
            mls_tracked_without_lot = self.env['stock.move.line'].browse(ml_ids_tracked_without_lot)
            products_list = "\n".join(f"- {product_name}" for product_name in mls_tracked_without_lot.mapped("product_id.display_name"))
            raise UserError(
                _("You need to supply a Lot/Serial Number for product:\n%s" % products_list)
            )
        if ml_ids_to_create_lot:
            self.env['stock.move.line'].browse(ml_ids_to_create_lot)._create_and_assign_production_lot()

        mls_to_delete = self.env['stock.move.line'].browse(ml_ids_to_delete)
        mls_to_delete.unlink()

        mls_todo = (self - mls_to_delete)
        mls_todo._check_company()

        ml_ids_to_ignore = OrderedSet()
        quants_cache = self.env['stock.quant']._get_quants_by_products_locations(
            mls_todo.product_id,
            mls_todo.location_id | mls_todo.location_dest_id,
            extra_domain=['|', ('lot_id', 'in', mls_todo.lot_id.ids), ('lot_id', '=', False)]
        )

        for ml in mls_todo.with_context(quants_cache=quants_cache):
            ml._synchronize_quant(-ml.quantity_product_uom, ml.location_id, action="reserved")
            available_qty, in_date = ml._synchronize_quant(-ml.quantity_product_uom, ml.location_id)

            if ml.tonase_asli and ml.location_id.usage not in ('inventory', 'production'):
                quant_out = self.env['stock.quant'].search([
                    ('product_id', '=', ml.product_id.id),
                    ('location_id', '=', ml.location_id.id),
                    ('lot_id', '=', ml.lot_id.id if ml.lot_id else False),
                    ('package_id', '=', ml.package_id.id if ml.package_id else False),
                    ('owner_id', '=', ml.owner_id.id if ml.owner_id else False),
                ], order='in_date desc', limit=1)
                if quant_out:
                    quant_out.sudo().write({
                        'tonase_asli': quant_out.tonase_asli - ml.tonase_asli
                    })
                if ml.lot_id:
                    ml.lot_id.sudo().write({
                        'tonase_asli': ml.lot_id.tonase_asli - ml.tonase_asli
                    })

            ml._synchronize_quant(
                ml.quantity_product_uom,
                ml.location_dest_id,
                package=ml.result_package_id,
                in_date=in_date
            )

            if ml.tonase_asli:
                quant_in = self.env['stock.quant'].search([
                    ('product_id', '=', ml.product_id.id),
                    ('location_id', '=', ml.location_dest_id.id),
                    ('lot_id', '=', ml.lot_id.id if ml.lot_id else False),
                    ('package_id', '=', ml.result_package_id.id if ml.result_package_id else False),
                    ('owner_id', '=', ml.owner_id.id if ml.owner_id else False),
                ], order='in_date desc', limit=1)
                if quant_in:
                    quant_in.sudo().write({
                        'tonase_asli': quant_in.tonase_asli + ml.tonase_asli
                    })
                if ml.lot_id:
                    ml.lot_id.sudo().write({
                        'tonase_asli': ml.lot_id.tonase_asli + ml.tonase_asli
                    })

            if available_qty < 0:
                ml._free_reservation(
                    ml.product_id, ml.location_id,
                    abs(available_qty),
                    lot_id=ml.lot_id, package_id=ml.package_id,
                    owner_id=ml.owner_id, ml_ids_to_ignore=ml_ids_to_ignore
                )

            ml_ids_to_ignore.add(ml.id)

        mls_todo.write({
            'date': fields.Datetime.now(),
        })

    @api.model
    def get_paginated_move_lines(self, picking_id, offset=0, limit=10, search=""):
        domain = [
            ("picking_id", "=", picking_id)
        ]

        if search:
            domain += [
                "|",
                ("product_id.name", "ilike", search),
                ("lot_id.name", "ilike", search),
            ]

        total = self.search_count(domain)
        records = self.search(domain, offset=offset, limit=limit, order="id desc",)

        result = []

        for rec in records:
            result.append({
                "id": rec.id,
                "product": rec.product_id.display_name,
                "lot": rec.lot_id.name,
                "quantity": rec.quantity,
            })

        return {
            "total": total,
            "records": result,
        }

    @api.onchange('product_id', 'move_id')
    def _onchange_product_uom_id(self):
        for line in self:
            if not line.product_id:
                continue

            if line.from_wizard:
                continue

            if line.move_id and line.move_id.product_uom:
                line.product_uom_id = line.move_id.product_uom
            else:
                line.product_uom_id = line.product_id.uom_id    

    @api.model
    def create(self, vals):
        if not vals.get('from_wizard'):
            if not vals.get('product_uom_id') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])

                if vals.get('move_id'):
                    move = self.env['stock.move'].browse(vals['move_id'])
                    vals['product_uom_id'] = move.product_uom.id or product.uom_id.id
                else:
                    vals['product_uom_id'] = product.uom_id.id

        return super().create(vals)

    def _find_or_create_move(self, product_uom_id):
        self.ensure_one()

        Move = self.env['stock.move']

        move = Move.search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', self.product_id.id),
            ('product_uom', '=', product_uom_id),
            ('state', 'not in', ('done', 'cancel')),
        ], limit=1)

        if move:
            return move

        return Move.sudo().with_context(
            tracking_disable=True,
            mail_notrack=True,
            mail_create_nosubscribe=True,
        ).create({
            'name': self.product_id.display_name,
            'product_id': self.product_id.id,
            'product_uom_qty': 0,
            'product_uom': product_uom_id,
            'picking_id': self.picking_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
        })        
    
    def write(self, vals):
        old_moves = self.mapped('move_id')
        uom_changed = 'product_uom_id' in vals

        res = super().write(vals)

        # =================================================
        # PINDAH MOVE JIKA UOM BERUBAH
        # =================================================
        if uom_changed:
            for line in self:

                target_move = line._find_or_create_move(
                    line.product_uom_id.id
                )

                if line.move_id != target_move:
                    line.sudo().with_context(
                        tracking_disable=True,
                        mail_notrack=True,
                        mail_create_nosubscribe=True,
                    ).write({
                        'move_id': target_move.id
                    })

        # =================================================
        # RECOMPUTE QTY
        # =================================================
        all_moves = old_moves | self.mapped('move_id')
        all_moves._recompute_quantities()

        return res

    def unlink(self):
        moves = self.mapped('move_id')
        res = super().unlink()
        moves._recompute_quantities()

        return res

    @api.constrains('product_uom_id', 'product_id')
    def _check_uom_category(self):
        for rec in self:
            if rec.product_uom_id and rec.product_id:
                if rec.product_uom_id.category_id != rec.product_id.uom_id.category_id:
                    raise ValueError("Kategori UoM tidak sesuai dengan produk.")
