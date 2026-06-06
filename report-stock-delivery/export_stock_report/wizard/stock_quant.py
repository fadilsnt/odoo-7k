from odoo import models, fields

class PengirimanReportWizard(models.TransientModel):
    _name = 'pengiriman.report.wizard'
    _description = 'Wizard Pengiriman Report by Warehouse'

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string="Warehouse",
        help="Kosongkan untuk semua warehouse"
    )

    kategori_selection = fields.Selection([
        ('all', 'All'),
        ('lokal', 'Lokal'),
        ('export', 'Export'),
    ], string="Kategori", default="all")

    end_date = fields.Date(
        string="End Date", default=fields.Date.context_today, required=True
    )

    sales_person_ids = fields.Many2many(
        'res.users',
        string='Sales Persons'
    )

    def action_print_report(self):
        return self.env.ref(
            'export_stock_report.action_report_dalam_pengiriman' 
        ).report_action(self)
    
