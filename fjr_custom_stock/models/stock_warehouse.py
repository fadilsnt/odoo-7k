from odoo import models, fields, api, _

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------
    
    allowed_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='res_users_allowed_stock_warehouse_rel',
        column1='warehouse_id',
        column2='user_id',
        string='Allowed Users',
        help='Users that are allowed to access this warehouse.'
    )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        print("self._context.get('display_all_warehouses', False)", self._context)
        if self.env.user.allowed_warehouse_ids and not self._context.get('display_all_warehouses', False):
            # If the user has specific allowed warehouses, filter by those
            domain = [('id', 'in', self.env.user.allowed_warehouse_ids.ids)] + domain
        return super(StockWarehouse, self)._search(domain, offset=offset, limit=limit, order=order)
    

    