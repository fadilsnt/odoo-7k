# -*- coding: utf-8 -*-
{
    'name': "Custom Inventory - Tuju Kuda",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Fajar - 0812 6888 8199",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'product', 'stock'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        # 'views/filter_produk.xml',
        'views/product_grade.xml',
        'views/stock_move.xml',
        'views/stock_quant.xml',
        'views/product_template.xml',
        'views/stock_move_line.xml',
        'views/res_users.xml',
        'views/stock_picking.xml',


        'menu.xml',
    ],
   
}

