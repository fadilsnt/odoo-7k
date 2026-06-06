from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    is_return_sparepart = fields.Boolean("Is Return Sparepart")
    origin_picking_id = fields.Many2one('stock.picking', string="Origin Picking")

    def _create_return(self):
        # Unreserve move
        for return_move in self.product_return_moves.move_id:
            return_move.move_dest_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )._do_unreserve()

        # Create return picking
        new_picking = self.picking_id.copy(self._prepare_picking_default_values())
        new_picking.user_id = False

        # Process lines
        returned_lines = False
        for return_line in self.product_return_moves:
            if return_line._process_line(new_picking):
                returned_lines = True

        if not returned_lines:
            raise UserError(_("Please specify at least one non-zero quantity."))

        new_picking.action_confirm()
        new_picking.action_assign()
        
        new_picking.origin_picking_id = self.picking_id.id

        new_picking.with_context(mail_notrack=True).message_post_with_source(
            'mail.message_origin_link',
            render_values={
                'self': new_picking,
                'origin': self.picking_id
            },
            subtype_xmlid='mail.mt_note',
        )

        if self.is_return_sparepart:
            self.picking_id.with_context(mail_notrack=True).message_post(
                body=_("Sparepart Return created: %s") % new_picking.display_name,
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

        return new_picking