from odoo import models, fields, api, _

class ProductProduct(models.Model):
    _inherit = 'product.product'

    owner_id = fields.Many2one(comodel_name='res.partner', related='product_tmpl_id.owner_id', store=True, readonly=False)
    sales_person_ids = fields.Many2many(comodel_name='res.users', related='product_tmpl_id.sales_person_ids', help='Sales persons who are responsible for this product template.')
    consume_product_ids = fields.Many2many(related='product_tmpl_id.consume_product_ids', string='Consume Products', readonly=True)

    # =========================================================
    # TONASE METRICS
    # =========================================================
    tonase_asli_available_qty = fields.Float('Tonase On Hand', compute='_compute_quantities_extended', compute_sudo=False)
    tonase_asli_free_qty = fields.Float('Free Tonase', compute='_compute_quantities_extended', compute_sudo=False)
    tonase_asli_incoming_qty = fields.Float('Incoming Tonase', compute='_compute_quantities_extended', compute_sudo=False)
    tonase_asli_outgoing_qty = fields.Float('Outgoing Tonase', compute='_compute_quantities_extended', compute_sudo=False)

    # =========================================================
    # COMPUTE
    # =========================================================
    @api.depends_context(
        'lot_id', 'owner_id', 'package_id',
        'from_date', 'to_date',
        'location', 'warehouse_id',
        'allowed_company_ids', 'is_storable'
    )
    def _compute_quantities_extended(self):
        self._compute_quantities()

        products = self.filtered(lambda p: p.type != 'service')

        Quant = self.env['stock.quant'].with_context(active_test=False)
        Move = self.env['stock.move'].with_context(active_test=False)

        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = self._get_domain_locations()

        domain_quant = [('product_id', 'in', products.ids)] + domain_quant_loc
        domain_move_in = [('product_id', 'in', products.ids)] + domain_move_in_loc
        domain_move_out = [('product_id', 'in', products.ids)] + domain_move_out_loc

        # =========================================================
        # FILTER CONTEXT
        # =========================================================
        if self.env.context.get('lot_id'):
            domain_quant.append(('lot_id', '=', self.env.context['lot_id']))

        if self.env.context.get('owner_id'):
            domain_quant.append(('owner_id', '=', self.env.context['owner_id']))
            domain_move_in.append(('restrict_partner_id', '=', self.env.context['owner_id']))
            domain_move_out.append(('restrict_partner_id', '=', self.env.context['owner_id']))

        if self.env.context.get('package_id'):
            domain_quant.append(('package_id', '=', self.env.context['package_id']))

        # =========================================================
        # QUANT TONASE
        # =========================================================
        quant_res = {
            product.id: (tonase, reserved)
            for product, tonase, reserved in Quant._read_group(
                domain_quant,
                ['product_id'],
                ['tonase_asli:sum', 'reserved_tonase_asli:sum']
            )
        }

        # =========================================================
        # MOVE TONASE
        # =========================================================
        domain_move_in = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_in
        domain_move_out = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_out

        incoming_res = {
            product.id: tonase
            for product, tonase in Move._read_group(
                domain_move_in,
                ['product_id'],
                ['tonase_asli:sum']
            )
        }

        outgoing_res = {
            product.id: tonase
            for product, tonase in Move._read_group(
                domain_move_out,
                ['product_id'],
                ['tonase_asli:sum']
            )
        }

        # =========================================================
        # ASSIGN RESULT
        # =========================================================
        for product in products:
            pid = product._origin.id

            tonase, reserved = quant_res.get(pid, (0.0, 0.0))
            incoming = incoming_res.get(pid, 0.0)
            outgoing = outgoing_res.get(pid, 0.0)

            # =====================================================
            # CORRECT ODOO-LIKE LOGIC
            # =====================================================

            product.tonase_asli_available_qty = tonase
            product.tonase_asli_free_qty = tonase - reserved - outgoing
            product.tonase_asli_incoming_qty = incoming
            product.tonase_asli_outgoing_qty = outgoing

        # =========================================================
        # SERVICES = 0
        # =========================================================
        (self - products).write({
            'tonase_asli_available_qty': 0.0,
            'tonase_asli_free_qty': 0.0,
            'tonase_asli_incoming_qty': 0.0,
            'tonase_asli_outgoing_qty': 0.0,
        })