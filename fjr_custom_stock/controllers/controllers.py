# -*- coding: utf-8 -*-
# from odoo import http


# class FjrCustomStock(http.Controller):
#     @http.route('/fjr_custom_stock/fjr_custom_stock', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/fjr_custom_stock/fjr_custom_stock/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('fjr_custom_stock.listing', {
#             'root': '/fjr_custom_stock/fjr_custom_stock',
#             'objects': http.request.env['fjr_custom_stock.fjr_custom_stock'].search([]),
#         })

#     @http.route('/fjr_custom_stock/fjr_custom_stock/objects/<model("fjr_custom_stock.fjr_custom_stock"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('fjr_custom_stock.object', {
#             'object': obj
#         })

