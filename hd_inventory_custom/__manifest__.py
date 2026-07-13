# -*- coding: utf-8 -*-
{
    'name': "Heptacloud Dvintara Inventory Custom",
    'summary': "Custom inventory features and enhancements for Heptacloud Dvintara.",
    'description': """
        This module provides additional customizations and enhancements
        for the inventory management workflow in Heptacloud Dvintara.
    """,
    'author': "Michael Hubert",
    'website': "https://www.linkedin.com/in/michael-hubert/",
    'maintainer': "Michael Hubert",
    'support': "echovoid14@gmail.com",
    'category': 'Inventory',
    'version': '0.1',
    'depends': [
        'base', 'mail', 'web', 'product', 'stock', 'fjr_custom_stock', 'export_stock_report', 
        'report_xlsx', 'uom', 'purchase', 'purchase_stock', 'repack_stock'
    ],
    'data': [
        'security/inventory_security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizards/wizard_inventory_laporan_hari_pengganti_view.xml',
        'wizards/wizard_buat_laporan_harian_picking_view.xml',
        'wizards/wizard_laporan_sparepart_bulanan_view.xml',
        'wizards/stock_opname_wizard.xml',
        'views/product_template_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_move_line_inherit_view.xml',
        'views/uom_uom_views.xml',
        'views/purchase_views.xml',
        'views/product_attribute_views.xml',
        'views/stock_quant_views.xml',
        'views/stock_move_views.xml',
        'views/product_views.xml',
        'reports/paperformat.xml',
        'reports/report_action.xml',
        'reports/bukti_terima_barang_pdf_report.xml',
        'reports/bukti_terima_barang_pdf_report_inventory.xml',
    ],
    'assets': {
        "web._assets_primary_variables": [],
        'web.assets_backend': [
            'hd_inventory_custom/static/src/js/purchase_order_list.js',
            'hd_inventory_custom/static/src/js/purchase_date_search.js',
            'hd_inventory_custom/static/src/js/purchase_dashboard.js',
            'hd_inventory_custom/static/src/xml/purchase_dashboard.xml',
            'hd_inventory_custom/static/src/css/header.css',
            'hd_inventory_custom/static/src/one2manysearch/one2manysearch.js',
            'hd_inventory_custom/static/src/one2manysearch/one2manysearch_template.xml',  
            # 'hd_inventory_custom/static/src/one2manysearch/css/one2many_search.css',          
        ],
        
    },    
    'phone': "085156534679",
}
