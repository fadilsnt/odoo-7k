# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    owner_id = fields.Many2one(comodel_name='res.partner', string="Pemilik", related='product_id.owner_id', store=True, readonly=False)
    sales_person_ids = fields.Many2many('res.users', string="Sales Persons", compute='_compute_sales_person_ids', inverse='_inverse_sales_person_ids', store=False)
    is_consume = fields.Boolean(string="Is Consume", default=False)
    sparepart_category_id = fields.Many2one('product.category', string="Sparepart Category", default=lambda self: self.env.ref('hd_inventory_custom.product_category_sparepart', raise_if_not_found=False))
    tonase_asli = fields.Float(string="Tonase Asli")
    tonase_asli_demand = fields.Float(string="Tonase Asli Demand")
    is_tonase_move_line = fields.Boolean(string="is Tonase Move Line?", compute="_compute_is_tonase_move_line", default=False)

    # =========================================================
    # PHYSICAL INVENTORY
    # =========================================================
    notes = fields.Text(string="Keterangan")

    @api.depends('move_line_ids')
    def _compute_is_tonase_move_line(self):
        for rec in self:
            _logger.info(
                "PICKING: %s, MOVE %s -> move_line_ids=%s",
                rec.picking_id,
                rec.id,
                rec.move_line_ids.ids
            )
            rec.is_tonase_move_line = bool(rec.move_line_ids)

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super()._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant)
        vals['tonase_asli'] = self.tonase_asli
        return vals    
    
    @api.model
    def create(self, vals):
        if 'tonase_asli' not in vals and 'tonase_asli_demand' in vals:
            vals['tonase_asli'] = vals['tonase_asli_demand']
        return super().create(vals)    

    @api.depends('product_id.sales_person_ids')
    def _compute_sales_person_ids(self):
        for move in self:
            move.sales_person_ids = move.product_id.sales_person_ids

    def _inverse_sales_person_ids(self):
        for move in self:
            move.product_id.sales_person_ids = move.sales_person_ids

    def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
        vals = super()._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant)

        if not vals.get('owner_id') and self.owner_id:
            vals['owner_id'] = self.owner_id.id

        return vals
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                vals['name'] = product.display_name

        return super().create(vals_list)    
    
    def write(self, vals):
        if vals.get('product_id') and not vals.get('name'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['name'] = product.display_name

        return super().write(vals)    
    
    def _recompute_quantities(self):
        for move in self:
            total_qty = sum(
                move.move_line_ids.filtered(
                    lambda l: l.state != 'cancel'
                ).mapped('quantity')
            )

            move.sudo().with_context(
                tracking_disable=True,
                mail_notrack=True,
                mail_create_nosubscribe=True,
                mail_auto_subscribe_no_notify=True,
                mail_post_autofollow=False,
            ).update({
                'product_uom_qty': total_qty
            })