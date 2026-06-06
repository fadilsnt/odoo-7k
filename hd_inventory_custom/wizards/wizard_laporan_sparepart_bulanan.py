from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import date

class WizardLaporanSparepartBulanan(models.TransientModel):
    _name = "wizard.laporan.sparepart.bulanan"
    _description = "Wizard Laporan Sparepart Bulanan"

    warehouse_id = fields.Many2many(comodel_name='stock.warehouse', string="Warehouse")
    start_date = fields.Date(string="Date", required=True, default=lambda self: date.today().replace(day=1))
    end_date = fields.Date(string="End Date", required=True, default=lambda self: (date.today().replace(day=1) + relativedelta(months=1, days=-1)))
    is_all_warehouse = fields.Boolean(string="Is All Warehouse", default=False)

    def action_print_report(self):
        return self.env.ref('hd_inventory_custom.report_laporan_sparepart_xlsx').report_action(self)