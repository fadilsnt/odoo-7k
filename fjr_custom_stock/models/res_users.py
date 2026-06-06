from odoo import models, fields, api, _

class ResUsers(models.Model):
    _inherit = 'res.users'


    allowed_warehouse_ids = fields.Many2many(
        comodel_name='stock.warehouse',
        relation='res_users_allowed_stock_warehouse_rel',
        column1='user_id',
        column2='warehouse_id',
        string='Allowed Warehouses',
        help='Warehouses that this user is allowed to access.'
    )

    customer = fields.Boolean('Customer')

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._update_customer_group()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'customer' in vals:
            self._update_customer_group()
        return res

    def _update_customer_group(self):
        group = self.env.ref('fjr_custom_stock.group_customer_product_limited', raise_if_not_found=False)
        if not group:
            return
        for user in self:
            if user.customer:
                group.sudo().write({'users': [(4, user.id)]})
            else:
                group.sudo().write({'users': [(3, user.id)]})
