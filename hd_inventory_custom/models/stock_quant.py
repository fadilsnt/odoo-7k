from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # =========================================================
    # BASE TONASE
    # =========================================================
    tonase_asli = fields.Float(string='Tonase Asli', readonly=True, digits='Product Unit of Measure',)
    reserved_tonase_asli = fields.Float(string='Reserved Tonase Asli', readonly=True, default=0.0, digits='Product Unit of Measure',)
    available_tonase_asli = fields.Float(string='Available Tonase Asli', compute='_compute_available_tonase_asli', store=True, digits='Product Unit of Measure',)

    # =========================================================
    # INVENTORY TONASE
    # =========================================================
    inventory_tonase_asli = fields.Float( string='Counted Tonase Asli', digits='Product Unit of Measure', help='Hasil stock opname tonase')
    inventory_tonase_asli_auto_apply = fields.Float( string='Inventoried Tonase Asli', compute='_compute_inventory_tonase_asli_auto_apply', inverse='_set_inventory_tonase_asli', groups='stock.group_stock_manager', digits='Product Unit of Measure')
    inventory_tonase_asli_diff = fields.Float( string='Tonase Difference', compute='_compute_inventory_tonase_asli_diff', store=True, readonly=True, digits='Product Unit of Measure', help='Selisih tonase teoritis vs hasil hitung')    

    # =========================================================
    # PHYSICAL INVENTORY
    # =========================================================
    notes = fields.Text(string="Keterangan")

    def _apply_inventory(self):
        res = super()._apply_inventory()

        for quant in self:
            if quant.inventory_tonase_asli is not None:
                quant.tonase_asli = quant.inventory_tonase_asli

        self.notes = ''
        return res

    def _get_inventory_move_values(
        self, qty,
        location_id,
        location_dest_id,
        package_id=False,
        package_dest_id=False
    ):
        vals = super()._get_inventory_move_values(
            qty,
            location_id,
            location_dest_id,
            package_id=package_id,
            package_dest_id=package_dest_id
        )

        # =====================================================
        # TONASE INJECTION (INVENTORY CONTEXT ONLY)
        # =====================================================
        tonase = self.env.context.get('inventory_tonase_asli', 0.0)

        if tonase:
            vals['move_line_ids'][0][2]['tonase_asli'] = tonase
        
        if self.notes:
            vals['notes'] = self.notes

        return vals

    @api.depends('tonase_asli', 'reserved_tonase_asli')
    def _compute_available_tonase_asli(self):
        for quant in self:
            quant.available_tonase_asli = quant.tonase_asli - quant.reserved_tonase_asli

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity=False, reserved_quantity=False,
                                   lot_id=None, package_id=None, owner_id=None, in_date=None):
        if not (quantity or reserved_quantity):
            raise ValidationError(_('Quantity or Reserved Quantity should be set.'))
        self = self.sudo()
        tonase_asli = self.env.context.get('tonase_asli', 0.0)
        reserved_tonase_asli = self.env.context.get('reserved_tonase_asli', 0.0)

        quants = self._gather(product_id, location_id, lot_id=lot_id,
                              package_id=package_id, owner_id=owner_id, strict=True)
        if lot_id and quantity > 0:
            quants = quants.filtered(lambda q: q.lot_id)

        if location_id.should_bypass_reservation():
            incoming_dates = []
        else:
            incoming_dates = [q.in_date for q in quants if q.in_date and
                              float_compare(q.quantity, 0, precision_rounding=q.product_uom_id.rounding) > 0]
        if in_date:
            incoming_dates += [in_date]
        in_date = min(incoming_dates) if incoming_dates else fields.Datetime.now()

        quant = None
        if quants:
            self._cr.execute("""
                SELECT id FROM stock_quant WHERE id IN %s ORDER BY lot_id LIMIT 1
                FOR NO KEY UPDATE SKIP LOCKED
            """, [tuple(quants.ids)])
            stock_quant_result = self._cr.fetchone()
            if stock_quant_result:
                quant = self.browse(stock_quant_result[0])

        if quant:
            vals = {'in_date': in_date}
            if quantity:
                vals['quantity'] = quant.quantity + quantity
            if reserved_quantity:
                vals['reserved_quantity'] = max(0, quant.reserved_quantity + reserved_quantity)
            if tonase_asli:
                vals['tonase_asli'] = quant.tonase_asli + tonase_asli
            if reserved_tonase_asli:
                vals['reserved_tonase_asli'] = max(0, quant.reserved_tonase_asli + reserved_tonase_asli)
            quant.write(vals)
        else:
            vals = {
                'product_id': product_id.id,
                'location_id': location_id.id,
                'lot_id': lot_id.id if lot_id else False,
                'package_id': package_id.id if package_id else False,
                'owner_id': owner_id.id if owner_id else False,
                'in_date': in_date,
                'quantity': quantity or 0.0,
                'reserved_quantity': reserved_quantity or 0.0,
                'tonase_asli': tonase_asli or 0.0,
                'reserved_tonase_asli': reserved_tonase_asli or 0.0,
            }
            quant = self.create(vals)

        return self._get_available_quantity(
            product_id, location_id,
            lot_id=lot_id, package_id=package_id, owner_id=owner_id,
            strict=True, allow_negative=True
        ), in_date

    @api.depends('tonase_asli')
    def _compute_inventory_tonase_asli_auto_apply(self):
        for quant in self:
            quant.inventory_tonase_asli_auto_apply = quant.tonase_asli

    @api.depends('inventory_tonase_asli', 'tonase_asli')
    def _compute_inventory_tonase_asli_diff(self):
        for quant in self:
            if not quant.inventory_tonase_asli:
                quant.inventory_tonase_asli_diff = 0.0
                continue

            diff = quant.inventory_tonase_asli - quant.tonase_asli

            quant.inventory_tonase_asli_diff = diff
            
    def _set_inventory_tonase_asli(self):
        if not self._is_inventory_mode():
            return

        for quant in self:
            quant.inventory_tonase_asli = quant.inventory_tonase_asli_auto_apply