# -*- coding: utf-8 -*-
from odoo import models, api, fields, _
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import logging
from odoo.tools.float_utils import float_compare, float_is_zero
from collections import defaultdict
from odoo.exceptions import UserError, ValidationError
import re

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    pemilik_ids = fields.Many2many('res.partner', 'stock_picking_owner_rel', 'picking_id', 'owner_id', string="Owners", help="Owner yang terlibat pada stock move.")
    btb_number = fields.Char(string="No. BTB", readonly=False, copy=False)
    partner_ref = fields.Char('Vendor Reference', copy=False, help="Reference of the sales order or bid sent by the vendor.")
    consume_move_ids = fields.One2many('stock.move', 'picking_id', string='Consume Moves', domain=[('is_consume', '=', True)])    
    move_ids_without_package = fields.One2many('stock.move', 'picking_id', string="Stock move", domain=['|', ('package_level_id', '=', False), ('picking_type_entire_packs', '=', False), ('is_consume', '=', False)])    
    sparepart_usage_attachment = fields.Many2many('ir.attachment', 'stock_picking_sparepart_attachment_rel', 'picking_id', 'attachment_id', string="Damage Evidence Attachment", help="Lampiran bukti sparepart sebelumnya rusak.")
    is_sparepart_usage = fields.Boolean(string="Is Sparepart Usage", compute="_compute_is_sparepart_usage", store=True)
    requestor_id = fields.Many2one('res.users', string='Requestor', tracking=True, states={'draft': [('readonly', False)]},)
    return_picking_ids = fields.One2many('stock.picking', 'origin_picking_id', string="Return Pickings")    
    return_count = fields.Integer(string="Return Count", compute="_compute_return_count")
    origin_picking_id = fields.Many2one('stock.picking', string="Origin Pickings")

    def _compute_return_count(self):
        for rec in self:
            rec.return_count = self.env['stock.picking'].search_count([('origin_picking_id', '=', rec.id)])    

    def action_view_return_pickings(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Pickings'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('origin_picking_id', '=', self.id)],
            'context': {'default_origin_picking_id': self.id}
        }            

    def action_return_sparepart(self):
        self.ensure_one()

        return {
            'name': _('Return Sparepart'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.return.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': self.ids,
                'active_model': 'stock.picking',
                'default_is_return_sparepart': True
            }
        }    

    @api.depends('picking_type_id')
    def _compute_is_sparepart_usage(self):
        picking_type = self.env.ref('hd_inventory_custom.picking_type_sparepart_usage', raise_if_not_found=False)

        for rec in self:
            rec.is_sparepart_usage = bool(
                picking_type
                and rec.picking_type_id.id == picking_type.id
            )

    def _validate_consume_products(self, picking):
        errors = []
        valid_moves = []

        scrap_location = self._get_scrap_location(picking)
        root_location = picking.location_dest_id
        grouped_qty = defaultdict(float)
        product_map = {}

        for line in picking.move_ids_without_package:
            qty = sum(line.move_line_ids.mapped('quantity'))

            if not qty:
                continue

            for cp in line.product_id.consume_product_ids:
                grouped_qty[cp.id] += qty

                if cp.id not in product_map:
                    product_map[cp.id] = {
                        'cp': cp,
                        'parents': set()
                    }

                product_map[cp.id]['parents'].add(line.product_id.display_name)

        for product_id, total_qty in grouped_qty.items():
            cp = product_map[product_id]['cp']
            parents = product_map[product_id]['parents']            

            quants = self.env['stock.quant'].search([
                ('product_id', '=', product_id),
                ('location_id', 'child_of', root_location.id),
            ])

            available_qty = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))

            if float_compare(available_qty, total_qty, precision_rounding=cp.uom_id.rounding) < 0:
                errors.append(
                    f"{', '.join(sorted(parents))} → {cp.display_name}\n"
                    f"Stock: {available_qty} | Need: {total_qty}"
                )
            else:
                valid_moves.append({
                    'name': f"Consume for {', '.join(parents)}",
                    'product_id': cp.id,
                    'product_uom': cp.uom_id.id,
                    'product_uom_qty': total_qty,
                    'location_id': root_location.id,
                    'location_dest_id': scrap_location.id,
                    'picking_id': picking.id,
                    'is_consume': True,
                })

        if errors:
            raise UserError(
                "Stock tidak cukup:\n\n" + "\n\n".join(errors)
            )

        return valid_moves

    def _get_scrap_location(self, picking):
        scrap_location = self.env['stock.location'].search([
            ('scrap_location', '=', True),
            ('company_id', 'in', [picking.company_id.id, False])
        ], limit=1)

        if not scrap_location:
            raise UserError("Scrap location tidak ditemukan!")

        return scrap_location

    # def _compute_btb_number_old(self):
    #     for picking in self.filtered(lambda p: p.picking_type_code == 'incoming'):
    #         date_ref = picking.scheduled_date or picking.create_date
    #         date_ref = fields.Datetime.context_timestamp(picking, date_ref)

    #         tahun = date_ref.strftime('%y')
    #         bulan_romawi = self._get_bulan_romawi(date_ref.month)

    #         start_month = date_ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    #         end_month = (start_month + relativedelta(months=1)) - timedelta(microseconds=1)
    #         warehouse_id = picking.picking_type_id.warehouse_id.id

    #         domain = [
    #             ('picking_type_code', '=', 'incoming'),
    #             ('btb_number', '!=', False),
    #             ('scheduled_date', '>=', start_month),
    #             ('scheduled_date', '<=', end_month),
    #             ('picking_type_id.warehouse_id', '=', warehouse_id),
    #         ]

    #         last = self.env['stock.picking'].sudo().search(domain, order='id desc', limit=1)

    #         if last and last.btb_number:
    #             try:
    #                 last_urutan = int(last.btb_number.split('/')[1])
    #                 urutan = last_urutan + 1
    #             except Exception:
    #                 urutan = 1
    #         else:
    #             urutan = 1

    #         warehouse = picking.picking_type_id.warehouse_id
    #         warehouse_code = warehouse.code if warehouse else 'NA'

    #         btb_number = f"BTB/{urutan:02d}/{bulan_romawi}/{tahun}/{warehouse_code}"

    #         picking.sudo().write({'btb_number': btb_number})

    #         # update ke PO
    #         if picking.origin:
    #             po = self.env['purchase.order'].sudo().search([('name','=', picking.origin)], limit=1)
    #             if po:
    #                 po.write({'btb_number': btb_number})

    def _compute_btb_number(self):
        for picking in self.filtered(lambda p: p.picking_type_code == 'incoming'):
            date_ref = picking.scheduled_date or picking.create_date
            date_ref = fields.Datetime.context_timestamp(picking, date_ref)

            tahun = date_ref.strftime('%y')
            bulan_romawi = self._get_bulan_romawi(date_ref.month)

            start_month = date_ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_month = (start_month + relativedelta(months=1)) - timedelta(microseconds=1)

            warehouse = picking.picking_type_id.warehouse_id
            warehouse_id = warehouse.id
            warehouse_code = warehouse.code if warehouse else 'NA'

            domain = [
                ('picking_type_code', '=', 'incoming'),
                ('btb_number', '!=', False),
                ('scheduled_date', '>=', start_month),
                ('scheduled_date', '<=', end_month),
                ('picking_type_id.warehouse_id', '=', warehouse_id),
            ]

            existing_pickings = self.env['stock.picking'].sudo().search_fetch(domain, ['btb_number'])

            urutan = 1
            if existing_pickings:
                btb_urutan_list = []
                for pick in existing_pickings:
                    parts = pick.btb_number.split('/')
                    if len(parts) > 1:
                        digits = re.findall(r'^\d+', parts[1])
                        if digits:
                            btb_urutan_list.append(int(digits[0]))
                if btb_urutan_list:
                    urutan = max(btb_urutan_list) + 1

            btb_number = f"BTB/{urutan:02d}/{bulan_romawi}/{tahun}/{warehouse_code}"

            picking.sudo().write({'btb_number': btb_number})

            # update ke PO
            if picking.origin:
                po = self.env['purchase.order'].sudo().search([('name', '=', picking.origin)], limit=1)
                if po:
                    po.write({'btb_number': btb_number})

    def button_validate(self):
        for picking in self:
            if picking.is_sparepart_usage:
                for move in picking.move_ids_without_package:
                    if move.product_id.type != 'product':
                        continue

                    available_qty = move.product_id.with_context(
                        location=move.location_id.id
                    ).free_qty

                    if float_compare(
                        move.product_uom_qty,
                        available_qty,
                        precision_rounding=move.product_uom.rounding
                    ) > 0:

                        raise ValidationError(_(
                            "Insufficient stock for product %s\n\n"
                            "Available Stock : %s %s\n"
                            "Requested Qty   : %s %s"
                        ) % (
                            move.product_id.display_name,
                            available_qty,
                            move.product_uom.name,
                            move.product_uom_qty,
                            move.product_uom.name,
                        ))

        # self._compute_btb_number()
        res = super().button_validate()

        for picking in self:
            if self.env['stock.move'].search([
                ('picking_id', '=', picking.id),
                ('is_consume', '=', True)
            ]):
                continue

            consumed_moves = self._validate_consume_products(picking)

            if consumed_moves:
                moves = self.env['stock.move'].create(consumed_moves)

                moves._action_confirm()
                moves._action_assign()

                for move in moves:
                    if not move.move_line_ids:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'quantity': move.product_uom_qty,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })

                    else:
                        for ml in move.move_line_ids:
                            ml.quantity = move.product_uom_qty

                moves._action_done()

        return res
    
    def _get_bulan_romawi(self, bulan):
        romawi = {
            1: 'I', 2: 'II', 3: 'III', 4: 'IV',
            5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII',
            9: 'IX', 10: 'X', 11: 'XI', 12: 'XII'
        }
        return romawi.get(bulan, '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            picking_type_id = vals.get('picking_type_id', False)
            if picking_type_id:
                picking_type = self.env['stock.picking.type'].sudo().browse(picking_type_id)

                if picking_type.code == 'incoming':
                    warehouse = picking_type.warehouse_id
                    warehouse_code = warehouse.code if warehouse else 'NA'
                    warehouse_id = warehouse.id

                    scheduled_date = vals.get('scheduled_date', False) or fields.Datetime.now()
                    if isinstance(scheduled_date, str):
                        scheduled_date = fields.Datetime.from_string(scheduled_date)

                    date_ref = fields.Datetime.context_timestamp(self, scheduled_date)

                    tahun = date_ref.strftime('%y')
                    bulan_romawi = self._get_bulan_romawi(date_ref.month)

                    start_month = date_ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    end_month = (start_month + relativedelta(months=1)) - timedelta(microseconds=1)

                    domain = [
                        ('picking_type_code', '=', 'incoming'),
                        ('btb_number', '!=', False),
                        ('scheduled_date', '>=', start_month),
                        ('scheduled_date', '<=', end_month),
                        ('picking_type_id.warehouse_id', '=', warehouse_id),
                    ]

                    existing_pickings = self.env['stock.picking'].sudo().search_fetch(domain, ['btb_number'])

                    urutan = 1
                    if existing_pickings:
                        btb_urutan_list = []
                        for pick in existing_pickings:
                            parts = pick.btb_number.split('/')
                            if len(parts) > 1:
                                digits = re.findall(r'^\d+', parts[1])
                                if digits:
                                    btb_urutan_list.append(int(digits[0]))
                        if btb_urutan_list:
                            urutan = max(btb_urutan_list) + 1

                    vals['btb_number'] = f"BTB/{urutan:02d}/{bulan_romawi}/{tahun}/{warehouse_code}"

        pickings = super().create(vals_list)
        for picking in pickings:
            if picking.picking_type_code == 'incoming' and picking.btb_number and picking.origin:
                po = self.env['purchase.order'].sudo().search([('name', '=', picking.origin)], limit=1)
                if po:
                    po.write({'btb_number': picking.btb_number})

        return pickings

    # @api.model
    # def create(self, vals):
    #     picking = super().create(vals)

    #     if picking.picking_type_code != 'incoming' or picking.btb_number:
    #         return picking

    #     date_now = fields.Datetime.context_timestamp(
    #         picking, fields.Datetime.now()
    #     )

    #     tahun = date_now.strftime('%y')
    #     bulan_romawi = self._get_bulan_romawi(date_now.month)

    #     start_month = date_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    #     end_month = (start_month + relativedelta(months=1)) - timedelta(microseconds=1)

    #     domain = [
    #         ('picking_type_code', '=', 'incoming'),
    #         ('btb_number', '!=', False),
    #         ('create_date', '>=', start_month),
    #         ('create_date', '<=', end_month),
    #     ]

    #     last = self.env['stock.picking'].sudo().search(
    #         domain,
    #         order='id desc',
    #         limit=1
    #     )

    #     if last and last.btb_number:
    #         try:
    #             last_urutan = int(last.btb_number.split('/')[1])
    #             urutan = last_urutan + 1
    #         except Exception:
    #             urutan = 1
    #     else:
    #         urutan = 1

    #     warehouse = picking.picking_type_id.warehouse_id
    #     warehouse_code = warehouse.code if warehouse else 'NA'

    #     btb_number = 'BTB/%02d/%s/%s/%s' % (urutan, bulan_romawi, tahun, warehouse_code)

    #     picking.sudo().write({'btb_number': btb_number})

    #     if picking.origin:
    #         po = self.env['purchase.order'].sudo().search([
    #             ('name', '=', picking.origin)
    #         ], limit=1)

    #         if po:
    #             po.write({'btb_number': btb_number})
    #     return picking

    def write(self, vals):
        res = super().write(vals)

        if 'move_ids' in vals:
            for picking in self:
                owners = picking.move_ids.mapped('owner_id')
                picking.with_context(skip_owner_sync=True).sudo().update({
                    'pemilik_ids': [(6, 0, owners.ids)]
                })

        return res

    def get_view(self, view_id=None, view_type="form", **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)

        if self.env.user.has_group('hd_inventory_custom.group_picking_view_only'):
            if view_type == "form":
                view = self.env.ref('hd_inventory_custom.view_picking_form_view_only').sudo()
                res['view_id'] = view.id
                res['arch'] = view.arch_db

            if view_type in ("list", "tree"):
                view = self.env.ref('hd_inventory_custom.vpicktree_custom_view_only').sudo()
                res['view_id'] = view.id
                res['arch'] = view.arch_db
        return res
