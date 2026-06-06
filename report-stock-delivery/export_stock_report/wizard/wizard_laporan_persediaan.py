from odoo import models, fields

KATEGORI_SELECTION = [
    ('all', 'All'),
    ('lokal', 'Lokal'),
    ('export', 'Export'),
    ('fuel', 'Fuel'),
]

class WizardLaporanPersediaan(models.TransientModel):
    _name = 'wizard.laporan.persediaan'
    _description = 'Wizard Stock Report by Warehouse'

    warehouse_ids = fields.Many2many('stock.warehouse', string="Warehouse", help="Kosongkan untuk semua warehouse")
    kategori_selection = fields.Selection(selection=KATEGORI_SELECTION, string="Kategori", default="all")
    end_date = fields.Date(string="End Date", default=fields.Date.context_today, required=True)
    sales_person_ids = fields.Many2many('res.partner', string='Sales Persons')

    def action_print_report(self):
        return self.env.ref('export_stock_report.action_report_stock_persediaan').report_action(self)
