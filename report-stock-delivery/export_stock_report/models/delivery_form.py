from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    sales_person_ids = fields.Many2many(
        'res.users',
        'stock_picking_sales_person_rel',   
        'picking_id',                       
        'user_id',                          
        string='Sales Persons'
    )

    person_ids = fields.Many2one(
        'res.users',
        string='Sales Person'
    )

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._update_sales_person_ids_from_moves()
        pickings._check_sales_person_responsible()
        return pickings

    def write(self, vals):
        if not self.env.context.get("skip_update_sales"):
            res = super().write(vals)
            self.with_context(skip_update_sales=True)._update_sales_person_ids_from_moves()
            self._check_sales_person_responsible()
            return res

        return super().write(vals)


    def _update_sales_person_ids_from_moves(self):
        for picking in self:
            all_sales = picking.move_ids_without_package.mapped("sales_person_ids")

            picking.with_context(skip_update_sales=True).write({
                "sales_person_ids": [(6, 0, all_sales.ids)]
            })

    def _check_sales_person_responsible(self):
        """Validasi: minimal satu sales picking harus ada di sales_product"""
        for picking in self:

            if not picking.sales_person_ids:
                continue  

            for move in picking.move_ids_without_package:
                product = move.product_id

                if product.sales_person_ids:
                    allowed_users = product.sales_person_ids
                    picking_users = picking.sales_person_ids

                    if not (allowed_users & picking_users):
                        raise UserError(_(
                            "Tidak ada Sales Person yang sesuai untuk produk '%s'.\n"
                            "Sales DO: %s\n"
                            "Sales yang boleh proses produk ini: %s"
                        ) % (
                            product.display_name,
                            ", ".join(picking_users.mapped("name")),
                            ", ".join(allowed_users.mapped("name")),
                        ))
