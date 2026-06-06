from odoo import models, api
from collections import defaultdict
import time
import re
import random


class ReportExportStock(models.AbstractModel):
    _name = 'report.export_stock_report.report_export_stock'
    _description = 'Report Export Stock'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['export.stock.wizard'].browse(docids)

        # ===== Domain picking =====
        move_domain = [
            ('picking_id.picking_type_code', '=', 'outgoing'),
            ('picking_id.scheduled_date', '>=', wizard.start_date),
            ('picking_id.scheduled_date', '<=', wizard.end_date),
            ('picking_id.picking_type_id.warehouse_id', 'in',
            wizard.warehouse_ids.ids or self.env['stock.warehouse'].search([]).ids),
            ('owner_id', 'in',
            wizard.sales_person_ids.ids or self.env['res.partner'].search([]).ids),
            ('state', 'not in', ['draft', 'cancel']),
        ]

        moves = self.env['stock.move'].search(move_domain)
        pickings = moves.mapped('picking_id')

        # ===== Struktur hasil utama =====
        results = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(lambda: {"box": 0, "cont": 0, "grade": None})
                )
            )
        )

        warehouses = set()
        products = set()
        grades = set()
        colors = ["#d97c7c", "#7c9bd9", "#7cd99b", "#d9b37c", "#9e7cd9"]
        bg_color = random.choice(colors)

        grand_totals = {"box": 0, "cont": 0}
        warehouse_totals = defaultdict(lambda: {"box": 0, "cont": 0})

        # ===== Loop picking & move line =====
        for picking in pickings:
            salespersons = moves.filtered(
                lambda m: m.picking_id == picking
            ).mapped('owner_id')

            salesperson = ", ".join(salespersons.mapped('name')) if salespersons else "-"

            # ambil sales person dari stock.move (user)
            sales_users = moves.filtered(
                lambda m: m.picking_id == picking
            ).mapped('sales_person_ids')

            # ambil partner dari user
            partners = sales_users.mapped('partner_id')

            # nama customer untuk grouping
            customer = ", ".join(partners.mapped('name')) if partners else "Unknown Customer"

            wh_name = picking.picking_type_id.warehouse_id.name
            warehouses.add(wh_name)

            for ml in picking.move_line_ids:
                categ_name = (ml.product_id.categ_id.name or "").lower()

                if wizard.kategori_selection == "export" and categ_name != "export":
                    continue
                elif wizard.kategori_selection == "lokal" and categ_name != "lokal":
                    continue

                prod = ml.product_id.display_name
                products.add(prod)
                pr_name = ml.product_id.name

                # Ambil grade dari nama produk (misal Product (A))
                match = re.search(r'\((.*?)\)', prod)
                grade_from_display_name = match.group(1) if match else None
                if grade_from_display_name:
                    grades.add(grade_from_display_name)

                qty = ml.quantity

                # Hitung box & cont
                box = qty
                # cont = qty / ml.product_id.container_capacity if ml.product_id.container_capacity else 0
                cont_capacity = self._get_cont_capacity(ml.product_id)
                cont = qty / cont_capacity if cont_capacity else 0

                # Simpan ke results
                results[salesperson][customer][prod][wh_name]["box"] += box
                results[salesperson][customer][prod][wh_name]["cont"] += cont
                results[salesperson][customer][prod][wh_name]["grade"] = grade_from_display_name
                results[salesperson][customer][prod][wh_name]["name_product"] = pr_name

                # Total per warehouse
                warehouse_totals[wh_name]["box"] += box
                warehouse_totals[wh_name]["cont"] += cont

                # Total global
                grand_totals["box"] += box
                grand_totals["cont"] += cont

        # ===== Tambahan: Konversi per UoM BOX =====
        # Ambil UoM dengan kategori BOX
        uoms = self.env['uom.uom'].search([('category_id.name', '=', 'BOX')], order="factor ASC")

        # Struktur simpan hasil konversi
        warehouse_uom_totals = defaultdict(lambda: defaultdict(float))
        grand_uom_totals = defaultdict(float)

        # Loop semua warehouse
        for wh_name in warehouses:
            qty_box = warehouse_totals[wh_name]["box"]

            # simpan total count asli (stok dasar BOX)
            warehouse_uom_totals[wh_name]['total_count'] += qty_box
            grand_uom_totals['total_count'] += qty_box

            for uom in uoms:
                if uom.factor:  # factor = berapa BOX dasar per UoM
                    converted_qty = qty_box / uom.factor
                else:
                    converted_qty = 0

                warehouse_uom_totals[wh_name][uom.id] += converted_qty
                grand_uom_totals[uom.id] += converted_qty

        return {
            "doc_ids": docids,
            "doc_model": "export.stock.report.wizard",
            "docs": wizard,
            "results": results,
            "warehouses": sorted(list(warehouses)),
            "products": sorted(list(products)),
            "grades": sorted(list(grades)),
            "time": time,
            "bg_color": bg_color,
            "grand_totals": grand_totals,
            "warehouse_totals": warehouse_totals,
            # tambahan untuk tabel baru
            "uoms": [{"id": u.id, "name": u.name, "factor": u.factor} for u in uoms],
            "warehouse_uom_totals": warehouse_uom_totals,
            "grand_uom_totals": grand_uom_totals,
        }
    
    def _get_cont_capacity(self, product):
        cont_attr = product.product_template_attribute_value_ids.filtered(
            lambda v: 'cont' in v.attribute_id.name.lower()
        )
        if cont_attr:
            try:
                return float(cont_attr[0].name)
            except:
                return 0
        return 0

