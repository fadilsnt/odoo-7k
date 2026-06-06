from odoo import models, api
from collections import defaultdict
import time
import re
import random
import logging

_logger = logging.getLogger(__name__)

class ReportStockWarehouse(models.AbstractModel):
    _name = 'report.export_stock_report.stok_persediaan_report'
    _description = 'Stock Report by Warehouse'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['wizard.laporan.persediaan'].browse(docids)
        if wizard.kategori_selection in ['all', 'lokal', 'export']:
            # ===== Domain picking =====
            move_domain = [
                ('picking_id.picking_type_code', '=', 'incoming'),
                ('picking_id.scheduled_date', '<=', wizard.end_date),
                (
                    'picking_id.picking_type_id.warehouse_id',
                    'in',
                    wizard.warehouse_ids.ids or self.env['stock.warehouse'].search([]).ids
                ),
                ('state', 'not in', ['draft', 'cancel']),
            ]

            # filter salesperson
            if wizard.sales_person_ids:
                move_domain.append(('owner_id', 'in', wizard.sales_person_ids.ids))

            moves = self.env['stock.move'].search(move_domain)
            _logger.info("MOVE COUNT = %s", len(moves))

            
            pickings = moves.mapped('picking_id')

            # ===== Struktur hasil utama =====
            results = defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(
                        lambda: defaultdict(lambda: {"box": 0, "cont": 0, "grade": None, "name_product": None})
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
            # ===== change here: customer_totals per warehouse + total =====
            customer_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0})))

            # ===== Loop picking & move line =====
            seen_quant = set()  # untuk menghindari double counting per (product, owner, warehouse)
            for picking in pickings:
                wh = picking.picking_type_id.warehouse_id
                wh_name = wh.name
                warehouses.add(wh_name)

                for ml in picking.move_line_ids:
                    # kategori filter tetap sama
                    categ_name = (ml.product_id.categ_id.name or "").lower()
                    if wizard.kategori_selection == "export" and categ_name != "export":
                        continue
                    elif wizard.kategori_selection == "lokal" and categ_name != "lokal":
                        continue

                    # ambil salesperson dari move
                    partner = ml.move_id.owner_id

                    _logger.info(
                        "MOVE=%s OWNER=%s",
                        ml.move_id.id,
                        partner.name if partner else "-"
                    )

                    if not partner:
                        continue

                    if wizard.sales_person_ids and partner.id not in wizard.sales_person_ids.ids:
                        continue

                    salesperson = partner.name
                    customer = partner.name
                    partner_ids = (partner.id,)

                    prod = ml.product_id.display_name
                    products.add(prod)
                    pr_name = ml.product_id.name

                    # Ambil grade dari nama produk (misal Product (A))
                    # match = re.search(r'\((.*?)\)', prod)
                    # grade_from_display_name = match.group(1) if match else None
                    grade_from_display_name = self._get_grade(ml.product_id)
                    if grade_from_display_name:
                        grades.add(grade_from_display_name)

                    # key untuk mencegah hitungan berulang sama (product, owner, warehouse)
                    seen_key = (ml.product_id.id, partner_ids, wh.id)
                    if seen_key in seen_quant:
                        # sudah dihitung quant untuk kombinasi ini => skip
                        continue
                    seen_quant.add(seen_key)

                    quant_domain = [
                        ('product_id', '=', ml.product_id.id),
                        ('location_id', 'child_of', wh.view_location_id.id),
                        # ('owner_id', 'in', partners.ids)
                    ]
                    
                    qty_onhand = sum(self.env['stock.quant'].search(quant_domain).mapped('quantity'))
                    qty = qty_onhand

                    box = qty
                    # cont = qty / ml.product_id.container_capacity if ml.product_id.container_capacity else 0
                    cont_capacity = self._get_cont_capacity(ml.product_id)
                    cont = qty / cont_capacity if cont_capacity else 0

                    # Simpan ke results
                    data_dict = results[salesperson][customer][prod][wh_name]
                    data_dict["box"] += box
                    data_dict["cont"] += cont
                    data_dict["grade"] = grade_from_display_name
                    data_dict["name_product"] = pr_name

                    # Total per warehouse
                    warehouse_totals[wh_name]["box"] += box
                    warehouse_totals[wh_name]["cont"] += cont

                    # === customer_totals: per warehouse ===
                    customer_totals[salesperson][customer][wh_name]["box"] += box
                    customer_totals[salesperson][customer][wh_name]["cont"] += cont
                    # and accumulate total under key "total"
                    customer_totals[salesperson][customer]["total"]["box"] += box
                    customer_totals[salesperson][customer]["total"]["cont"] += cont

                    # Total global
                    grand_totals["box"] += box
                    grand_totals["cont"] += cont

            # ===== Hitung total per produk (per warehouse & total) =====
            product_group_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0})))
            for sp, custs in results.items():
                for cust, prods in custs.items():
                    for prod_name, wh_data in prods.items():
                        base_name = re.sub(r'\s*\(.*?\)', '', prod_name).strip()
                        for wh_name, vals in wh_data.items():
                            product_group_totals[cust][base_name][wh_name]["box"] += vals.get("box", 0)
                            product_group_totals[cust][base_name][wh_name]["cont"] += vals.get("cont", 0)
                            product_group_totals[cust][base_name]["total"]["box"] += vals.get("box", 0)
                            product_group_totals[cust][base_name]["total"]["cont"] += vals.get("cont", 0)

            uoms = self.env['uom.uom'].search([('category_id.name', '=', 'BOX')], order="factor ASC")
            warehouse_uom_totals = defaultdict(lambda: defaultdict(float))
            grand_uom_totals = defaultdict(float)

            warehouse_uom_totals_count = defaultdict(lambda: defaultdict(float))
            grand_uom_totals_count = defaultdict(float)

            for wh_name in warehouses:
                qty_box = warehouse_totals[wh_name]["box"]
                qty_cont = warehouse_totals[wh_name]["cont"]

                # === versi dari BOX ===
                warehouse_uom_totals[wh_name]['total_count'] += qty_box
                grand_uom_totals['total_count'] += qty_box

                for uom in uoms:
                    converted_qty = qty_box / uom.factor if uom.factor else 0
                    warehouse_uom_totals[wh_name][uom.id] += converted_qty
                    grand_uom_totals[uom.id] += converted_qty

                # === versi dari COUNT ===
                warehouse_uom_totals_count[wh_name]['total_count'] += qty_cont
                grand_uom_totals_count['total_count'] += qty_cont

                for uom in uoms:
                    converted_qty_count = qty_cont / uom.factor if uom.factor else 0
                    warehouse_uom_totals_count[wh_name][uom.id] += converted_qty_count
                    grand_uom_totals_count[uom.id] += converted_qty_count

            # ===== TOTAL PER UoM PER WAREHOUSE (pivot) =====
            total_per_uom_warehouse = defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(lambda: defaultdict(float))
                )
            )
            # Struktur: total_per_uom_warehouse[uom_name][product][warehouse]['converted']

            for uom in uoms:
                uom_name = uom.name
                uom_factor = uom.factor or 1

                for sp, custs in results.items():
                    for cust, prods in custs.items():
                        for prod_name, wh_data in prods.items():
                            match = re.search(r'\((.*?)\)', prod_name)
                            grade = match.group(1) if match else None

                            for wh_name, vals in wh_data.items():
                                qty_box = vals.get("box", 0)
                                converted = qty_box / uom_factor if uom_factor else 0
                                total_per_uom_warehouse[uom_name][prod_name][wh_name]['converted'] += converted
                                total_per_uom_warehouse[uom_name][prod_name][wh_name]['grade'] = grade

            # ======== Tambahan baru: TOTAL KESELURUHAN PER WAREHOUSE (BARU) ========
            stock_domain = [
                ('date', '<=', wizard.end_date),
                ('state', 'not in', ['draft', 'cancel']),
                # ('location_dest_id.warehouse_id', 'in', wizard.warehouse_ids.ids),
            ]
            move_lines = self.env['stock.move.line'].search(stock_domain)

            total_warehouse_summary_new = defaultdict(lambda: defaultdict(float))
            grand_total_summary_new = defaultdict(float)
            all_uoms_new = set()

            for line in move_lines:
                wh = line.location_dest_id.warehouse_id
                if not wh:
                    continue
                wh_name = wh.name
                uom_name = line.product_uom_id.name or 'Unknown'

                total_warehouse_summary_new[wh_name][uom_name] += line.quantity
                total_warehouse_summary_new[wh_name]['Total Count (BOX)'] += line.quantity
                total_warehouse_summary_new[wh_name]['CONT'] += line.quantity / 3100
                all_uoms_new.add(uom_name)

            # === Hitung GRAND TOTAL ===
            for wh_data in total_warehouse_summary_new.values():
                for uom_name, qty in wh_data.items():
                    grand_total_summary_new[uom_name] += qty

            total_warehouse_summary_new['GRAND TOTAL'] = grand_total_summary_new
            total_warehouse_summary_new = dict(sorted(total_warehouse_summary_new.items(), key=lambda x: x[0].lower()))

            # === UoM yang muncul di data saja ===
            uoms_used_new = [{'name': name} for name in sorted(all_uoms_new)]

            # ====== Tambahan: Hitung Total per Salesperson ======
            salesperson_totals = defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0}))

            for sp, custs in customer_totals.items():
                for cust_name, whs in custs.items():
                    # akumulasi per warehouse dari customer_totals
                    for wh_name, vals in whs.items():
                        if wh_name == 'total':
                            continue
                        salesperson_totals[sp][wh_name]["box"] += vals.get("box", 0)
                        salesperson_totals[sp][wh_name]["cont"] += vals.get("cont", 0)

                    # total keseluruhan per salesperson
                    salesperson_totals[sp]["total"]["box"] += whs.get("total", {}).get("box", 0)
                    salesperson_totals[sp]["total"]["cont"] += whs.get("total", {}).get("cont", 0)

            # ====== Tambahan baru: Grand Total per Warehouse ======
            grand_totals_per_wh = defaultdict(lambda: {"box": 0, "cont": 0})
            grand_totals_per_wh["total"] = {"box": 0, "cont": 0}

            for sp, custs in customer_totals.items():
                for cust_name, whs in custs.items():
                    for wh_name, vals in whs.items():
                        if wh_name == "total":
                            continue
                        grand_totals_per_wh[wh_name]["box"] += vals.get("box", 0)
                        grand_totals_per_wh[wh_name]["cont"] += vals.get("cont", 0)
                        # Total keseluruhan semua warehouse
                        grand_totals_per_wh["total"]["box"] += vals.get("box", 0)
                        grand_totals_per_wh["total"]["cont"] += vals.get("cont", 0)

            if wizard.warehouse_ids:
                ordered_warehouses = wizard.warehouse_ids.mapped('name')
            else:
                ordered_warehouses = sorted(list(warehouses))

            return {
                "doc_ids": docids,
                "doc_model": "stock.report.wizard",
                "docs": wizard,
                "results": results,
                "warehouses": ordered_warehouses,
                "products": sorted(list(products)),
                "grades": sorted(list(grades)),
                "time": time,
                "bg_color": bg_color,
                "grand_totals": grand_totals,
                "warehouse_totals": warehouse_totals,
                "customer_totals": customer_totals,
                "uoms": [{"id": u.id, "name": u.name, "factor": u.factor} for u in uoms],
                "warehouse_uom_totals": warehouse_uom_totals,
                "grand_uom_totals": grand_uom_totals,
                "grand_uom_totals_count" : grand_uom_totals_count,
                "product_group_totals": product_group_totals,
                "uoms_new": uoms_used_new,
                "total_warehouse_summary_new": total_warehouse_summary_new,
                "salesperson_totals": salesperson_totals,
                "grand_totals_per_wh": grand_totals_per_wh,
            }
        else:
            #kategori fuel
            move_domain = [
                ('state', 'not in', ['draft', 'cancel']),
                ('date', '<=', wizard.end_date),
                ('location_dest_id.warehouse_id', 'in',
                wizard.warehouse_ids.ids or self.env['stock.warehouse'].search([]).ids),
            ]

            move_lines = self.env['stock.move.line'].search(move_domain)

            results = defaultdict(lambda: defaultdict(lambda: {
                "box": 0.0,
                "kg": 0.0,
                "cont": 0.0
            }))

            product_totals = defaultdict(lambda: {
                "box": 0.0,
                "kg": 0.0,
                "cont": 0.0
            })

            grand_total_cont = 0.0
            warehouse_totals = {"box": 0.0, "kg": 0.0, "cont": 0.0}

            seen = set()

            for line in move_lines:
                wh = line.location_dest_id.warehouse_id
                if not wh:
                    continue

                product = line.product_id
                if (product.categ_id.name or "").lower() != "fuel":
                    continue

                product_name = (product.name or '').upper()
                if product_name in ['SCRAP', 'FUEL JUMBO BAG']:
                    continue

                key = (wh.id, product.id)
                if key in seen:
                    continue
                seen.add(key)

                qty = line.quantity or line.product_uom_qty or 0.0
                uom = line.product_uom_id
                # =============================
                # DESIGN DARI UOM MOVE LINE
                # =============================
                design_name = f"{product.name} {uom.name}"

                # =============================
                # BOX = QTY MOVE LINE
                # =============================
                box = qty

                # =============================
                # KG = QTY x RATIO UOM MOVE LINE
                # =============================
                ratio = uom.ratio or 1
                kg = box * ratio

                # =============================
                # CONT (kalau masih pakai function lama)
                # =============================
                _, _, cont_capacity = self._get_fuel_variant_values(product)
                cont = box / cont_capacity if cont_capacity else 0.0

                # =============================
                # SIMPAN PER WAREHOUSE & DESIGN
                # =============================
                results[wh.name][design_name]["box"] += box
                results[wh.name][design_name]["kg"] += kg
                results[wh.name][design_name]["cont"] += cont

                # =============================
                # TOTAL PER DESIGN
                # =============================
                product_totals[design_name]["box"] += box
                product_totals[design_name]["kg"] += kg
                product_totals[design_name]["cont"] += cont

                # =============================
                # GRAND TOTAL
                # =============================
                warehouse_totals["box"] += box
                warehouse_totals["kg"] += kg
                warehouse_totals["cont"] += cont

                grand_total_cont += cont

             
            #product fuel jumbo bag 
            results_jumbo_bag = defaultdict(lambda: {
                "box": 0.0,
                "kg": 0.0,
                "cont": 0.0
            })

            jumbo_totals = {
                "box": 0.0,
                "kg": 0.0,
                "cont": 0.0,
            }

            seen = set()
            cont_value_jumbo = 0.0  # disimpan sekali, karena cuma 1 product

            for line in move_lines:
                wh = line.location_dest_id.warehouse_id
                if not wh:
                    continue

                product = line.product_id

                # === FILTER PRODUCT ===
                if (product.name or '').upper() != 'FUEL JUMBO BAG':
                    continue

                key = (wh.id, product.id)
                if key in seen:
                    continue
                seen.add(key)

                # === QTY BOX (ON HAND) ===
                quant_domain = [
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', wh.view_location_id.id),
                ]
                qty = sum(self.env['stock.quant'].search(quant_domain).mapped('quantity'))
                if not qty:
                    continue

                # === AMBIL CONT VALUE (1x saja) ===
                _, _, cont_value = self._get_fuel_variant_values(product)
                cont_value_jumbo = cont_value or cont_value_jumbo

                # === HITUNG PER WAREHOUSE ===
                box = qty
                kg = box * 500
                cont = kg / cont_value_jumbo if cont_value_jumbo else 0

                results_jumbo_bag[wh.name]["box"] = box
                results_jumbo_bag[wh.name]["kg"] = kg
                results_jumbo_bag[wh.name]["cont"] = cont

                # === AKUMULASI TOTAL BOX ===
                jumbo_totals["box"] += box

            jumbo_totals["kg"] = jumbo_totals["box"] * 500

            jumbo_totals["cont"] = (
                jumbo_totals["kg"] / cont_value_jumbo
                if cont_value_jumbo else 0
            )

            scrap_results = defaultdict(lambda: {
                "variants": {
                    'KRG 20 KG': 0.0,
                    'KRG 550 KG': 0.0,
                    'KRG 600 KG': 0.0,
                }
            })

            scrap_totals = {
                'qty_20': 0.0,
            }

            seen = set()

            for line in move_lines:
                wh = line.location_dest_id.warehouse_id
                if not wh:
                    continue

                product = line.product_id
                product_name = (product.name or '').upper()

                # === HANYA SCRAP ===
                if 'SCRAP' not in product_name:
                    continue

                key = (wh.id, product.id)
                if key in seen:
                    continue
                seen.add(key)

                # === QTY ON HAND ===
                quant_domain = [
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', wh.view_location_id.id),
                ]
                qty = sum(self.env['stock.quant'].search(quant_domain).mapped('quantity'))
                if not qty:
                    continue

                # === ISI KE KRG 20 KG ===
                scrap_results[wh.name]["variants"]['KRG 20 KG'] += qty

                # === TOTAL GLOBAL ===
                scrap_totals['qty_20'] += qty



            return {
                "docs": wizard,
                "results": results,
                "results_jumbo_bag": results_jumbo_bag,
                "jumbo_totals": jumbo_totals,
                "warehouse_totals": warehouse_totals,
                "scrap_results": scrap_results,
                "scrap_totals": scrap_totals,
                "product_totals": product_totals,
                "grand_total_cont": grand_total_cont,
            }
        


    def _get_fuel_variant_values(self, product):
        """
        return:
        design_name, kg_per_box, cont_value
        """

        box_name = product.name
        kg_per_box = 1
        cont_value = 0.0

        # === FIELD PRIORITY ===
        if getattr(product, 'kg_per_box', 0):
            kg_per_box = product.kg_per_box

        if getattr(product, 'cont_value', 0):
            cont_value = product.cont_value

        # === ATTRIBUTE FALLBACK ===
        for val in product.product_template_attribute_value_ids:
            val_name = val.name.upper()

            # Ambil ANGKA sebelum / diikuti KG
            if 'KG' in val_name:
                match = re.search(r'(\d+(\.\d+)?)\s*KG', val_name)
                if match:
                    kg_per_box = float(match.group(1))

            # Ambil angka murni (CONT biasanya angka saja)
            match_cont = re.search(r'\b(\d{3,})\b', val_name)
            if match_cont:
                cont_value = float(match_cont.group(1))

        # === DESIGN NAME ===
        if kg_per_box:
            design_name = f"{box_name} {int(kg_per_box)} KG"
        else:
            design_name = box_name

        return design_name, kg_per_box, cont_value
    
    def _get_scrap_variant_label(self, product):
        match = re.search(r'(\d+)\s*KG', (product.name or '').upper())
        if match:
            return f"KRG {match.group(1)} KG"
        return None

    
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
    
    def _get_grade(self, product):
        grade_attr = product.product_template_attribute_value_ids.filtered(
            lambda v: 'grade' in v.attribute_id.name.lower()
        )
        if grade_attr:
            return grade_attr[0].name
        return None
    
    def _get_grade_value(self, product):
        for val in product.product_template_attribute_value_ids:
            if 'grade' in val.attribute_id.name.lower():
                match = re.search(r'(\d+)', val.name)
                if match:
                    return float(match.group(1))
        return 0.0

