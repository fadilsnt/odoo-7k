from odoo import models, fields, api, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    owner_id = fields.Many2one(comodel_name='res.partner', help="Pemilik default untuk produk ini.")
    consume_product_ids = fields.Many2many('product.product', 'product_template_consume_rel', 'tmpl_id', 'consume_id', string='Consume Products', help="Produk yang akan otomatis terpakai saat produk ini diterima")
    is_cl = fields.Boolean(string="is CL?", default=False)