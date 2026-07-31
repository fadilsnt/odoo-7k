from odoo import models, fields
from datetime import datetime
from odoo.exceptions import UserError

SELECTION_REPORT_TYPE = [
    ('quantity_base', 'Laporan Export'),
    ('tonase_base', 'Tonasi Asli')
]

class WizardInventoryLaporanHariPengganti(models.TransientModel):
    _name = 'wizard.inventory.laporan.hari.pengganti'
    _description = "Wizard Inventory Laporan Hari Pengganti"

    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    warehouse_id = fields.Many2one(comodel_name='stock.warehouse', string="Warehouse", required=False)
    grade_value_ids = fields.Many2many('product.attribute.value', 'wizard_grade_value_ids', 'wizard_id', 'grade_value_id', string="Attribute Values", domain="[('attribute_id.name', 'in', ['grade','Grade','GRADE'])]")
    is_kotak = fields.Boolean(string="Is Kotak", default=False)
    report_type = fields.Selection(selection=SELECTION_REPORT_TYPE, string="Report Type", default='quantity_base')

    def action_print_xlsx_report(self):
        self.ensure_one()

        if len(self.grade_value_ids) > 5:
            raise UserError("Max 5 Grade Value for Average !")

        report_date = self.date.strftime('%d-%m-%Y')
        warehouse_name = self.warehouse_id.name if self.warehouse_id else 'Semua Gudang'
        filename = f"Laporan Harian {warehouse_name} - {report_date}"
        if self.report_type:
            filename += f" ({dict(SELECTION_REPORT_TYPE)[self.report_type]})"
        
        report_obj = self.env.ref('hd_inventory_custom.inventory_laporan_hari_pengganti_tonase_base_xlsx')
        
        if self.report_type == 'quantity_base':
            report_obj = self.env.ref('hd_inventory_custom.inventory_laporan_hari_pengganti_xlsx')

        report_obj.name = filename

        return report_obj.report_action(self, data={
            'date': self.date,
            'warehouse_id': self.warehouse_id.id if self.warehouse_id else False,
            'grade_value_ids': self.grade_value_ids.ids if self.grade_value_ids else False,
            'is_kotak': self.is_kotak,

        })
