from odoo import models, fields
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    repack_line_ids = fields.One2many(
        "stock.repack.line",
        "picking_id"
    )

    is_repack_done = fields.Boolean(default=False)

    def button_validate(self):

        for picking in self:

            if picking.repack_line_ids:
                StockMoveLine = self.env['stock.move.line']

                moves_b = []
                for line in picking.repack_line_ids:
                    StockMoveLine.create({
                        'product_id': line.product_a_id.id,
                        'product_uom_id': line.product_a_id.uom_id.id,
                        'quantity': line.qty_a,
                        'location_id': picking.location_id.id,      
                        'location_dest_id': picking.location_dest_id.id,
                        'company_id': picking.company_id.id,
                    })

                    StockMoveLine.create({
                        'product_id': line.product_a_id.id,
                        'product_uom_id': line.product_a_id.uom_id.id,
                        'quantity': line.qty_a,
                        'location_id': picking.location_dest_id.id,
                        'location_dest_id': picking.location_id.id,
                        'company_id': picking.company_id.id,
                    })
                    
                    for l in line.repack_output_ids:
                        moves_b.append((0, 0, {
                            'picking_id': picking.id,
                            'name': l.product_b_id.name,
                            'product_id': l.product_b_id.id,
                            'product_uom_qty': l.qty_b,
                            'quantity': l.qty_b,
                            'product_uom': l.product_b_id.uom_id.id,
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,
                            'company_id': picking.company_id.id,
                        }))
                picking.move_ids_without_package = moves_b

                picking.is_repack_done = True

        return super().button_validate()

    def action_repack(self):
        StockMoveLine = self.env['stock.move.line']

        for picking in self:

            moves_b = []
            for line in picking.repack_line_ids:
                StockMoveLine.create({
                    # 'picking_id': picking.id,
                    'product_id': line.product_a_id.id,
                    'product_uom_id': line.product_a_id.uom_id.id,
                    'quantity': line.qty_a,
                    'location_id': picking.location_id.id,      
                    'location_dest_id': picking.location_dest_id.id 
                })

                StockMoveLine.create({
                    # 'picking_id': picking.id,
                    'product_id': line.product_a_id.id,
                    'product_uom_id': line.product_a_id.uom_id.id,
                    'quantity': line.qty_a,
                    'location_id': picking.location_dest_id.id,
                    'location_dest_id': picking.location_id.id 
                })
                
                for l in line.repack_output_ids:
                    moves_b.append((0, 0, {
                        'picking_id': picking.id,
                        'name': l.product_b_id.name,
                        'product_id': l.product_b_id.id,
                        'product_uom_qty': l.qty_b,
                        'quantity': l.qty_b,
                        'product_uom': l.product_b_id.uom_id.id,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                    }))
            picking.move_ids_without_package = moves_b

            picking.is_repack_done = True
