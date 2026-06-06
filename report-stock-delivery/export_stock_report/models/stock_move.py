from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    no_cont = fields.Char(
        string='No. Container',
        help='Nomor container untuk pengiriman'
    )

    keterangan = fields.Char(
        string='Keterangan',
        help='Keterangan tambahan pengiriman'
    )

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        """
        Tambahkan no_cont sebagai pembeda
        agar stock.move TIDAK digabung jika no_cont berbeda
        """
        fields_list = super()._prepare_merge_moves_distinct_fields()
        return fields_list + ['no_cont']
