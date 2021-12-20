# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

from datetime import date
from datetime import datetime
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
import calendar
import re
import json
from dateutil.relativedelta import relativedelta
import pgeocode
import qrcode
from PIL import Image
from random import choice
from string import digits
import json
import re
import uuid
from functools import partial



class CashBookInfo(models.Model):
    _inherit = "cash.book.info"

    neft_id = fields.Many2one('neft.rtgs.collection')



class PartnerLedgerCustom(models.Model):
    _inherit = 'partner.ledger.customer'

    neft_id = fields.Many2one('neft.rtgs.collection')



class SupplierLedgerCustom(models.Model):
    _inherit = 'supplier.ledger.customer'

    neft_id = fields.Many2one('neft.rtgs.collection')



class RtgsNeftCollections(models.Model):
    _inherit = "neft.rtgs.collection"

    state = fields.Selection([('draft', 'Draft'), ('validate', 'Validate'),('return', 'Reversed'), ('cancelled', 'Cancelled')], readonly=True,
                             default='draft', copy=False, string="Status")


    def main_company_neft(self, type):
        stmt =state = self.env['account.bank.statement']
        # bal = sum(self.env['account.invoice'].search(
        #     [('company_id', '=', 1), ('partner_id', '=', self.accountant.id)]).mapped('amount_total_signed'))

        if not stmt:
            journ = self.env['account.journal'].search(
                [('name', '=', 'Bank'), ('company_id', '=', 1)])
            # bal = sum(self.env['account.move.line'].search([('journal_id', '=', journ.id)]).mapped(
            #     'debit'))

            if self.env['account.bank.statement'].search(
                    [('company_id', '=',journ.company_id.id), ('journal_id', '=', journ.id)]):
                bal = self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                    0].balance_end_real
            else:
                bal = 0

            # if self.env['partner.ledger.customer'].search(
            #     [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)]):
            #     bal = self.env['partner.ledger.customer'].search(
            #         [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)])[-1].balance

            stmt = self.env['account.bank.statement'].create({'name': self.accountant.name,
                                                              'balance_start': bal,
                                                              # 'journal_id': line.journal_id.id,
                                                              'journal_id': journ.id,
                                                              'balance_end_real': bal+self.amount_total
                                                              })

            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

            pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                                                         # 'amount': datev.amount_total,
                                                         'amount': self.amount_total,
                                                         'partner_type': self.partner_type,
                                                         'company_id': 1,
                                                         'payment_type': self.payment_type,
                                                         'payment_method_id': self.payment_method_id.id,
                                                         # 'journal_id': line.journal_id.id,
                                                         'journal_id': journ.id,
                                                         'communication': type + 'to ,from' + self.accountant.name + '=>' + journ.company_id.name + ',' + journ.name,

                                                         })
            pay_id.post()
            pay_id.action_cash_book()
            pay_id_list = []
            payment_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)
            product_line = (0, 0, {
                'date': self.payment_date,
                'name': self.type,
                'partner_id': self.partner_id.id,
                'ref': self.type,
                'amount': self.amount_total})
            payment_list.append(product_line)
            # invoices = self.env['account.invoice'].sudo().search(
            #     [('partner_id', '=', new_inv.partner_id.id), ('company_id', '=', new_inv.company_id.id),
            #      ('state', '!=', 'paid')])
            # if invoices.mapped('residual'):
            #     balance_amount = sum(invoices.mapped('residual'))
            # else:
            #     balance_amount = sum(invoices.mapped('amount_total'))
            balance_amount =0
            balance_amount += self.env['partner.ledger.customer'].sudo().search(
                [('partner_id', '=', self.accountant.id), ('description', '=', 'Opening Balance')]).balance
            Previous_led = self.env['partner.ledger.customer'].sudo().search(
                [('company_id', '=', 1), ('partner_id', '=', self.accountant.id)])
            if Previous_led:
                balance_amount = Previous_led[-1].balance

            self.env['partner.ledger.customer'].sudo().create({
                'date': datetime.today().date(),
                # 'invoice_id': inv.id,
                'description': type + '  ' + 'To' + '  ' + self.journal_id.company_id.name + ' ' + '& CO,' + 'A/C No:' + self.journal_id.default_debit_account_id.display_name + ' ' + 'on' + ' ' + str(
                    self.cleared_date),
                'partner_id': self.accountant.id,
                'company_id': 1,
                'check_only':True,
                'neft_id':self.id,
                'credit': self.amount_total,
                'balance': balance_amount - self.amount_total,
                'account_move': pay_id.move_line_ids.mapped('move_id')[0].id,
                'account_journal': self.journal_id.id
            })

        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})


    def action_confirm(self):
        if self.type != 'cheque':
            stmt = self.env['account.bank.statement']
            partner_led = self.env['partner.ledger.customer']
            if self.type == 'neft':
                type = 'NEFT'
            if self.type == 'rtgs':
                type = 'RTGS'
            if self.type == 'deposit':
                type = 'Deposit'
            if self.type == 'internal':
                type = 'Transfer'
            if self.type == 'cheque':
               type = 'Cheque'

            self.main_company_neft(type)
            self.write({'state':'validate'})
            payment_list = []
            pay_id_list = []
            account = self.env['account.invoice'].search(
                [('partner_id', '=', self.sub_partner.id), ('state', '=', 'open')])
            amount = self.amount_total
            actual = 0
            for datev in account:
                if not stmt:
                    # bal = sum(self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped(
                    #     'debit'))

                    if self.env['account.bank.statement'].search([('company_id', '=', self.journal_id.company_id.id),
                                                                  ('journal_id', '=', self.journal_id.id)]):
                        bal = self.env['account.bank.statement'].search(
                            [('company_id', '=', self.journal_id.company_id.id),
                             ('journal_id', '=', self.journal_id.id)])[0].balance_end_real
                    else:
                        bal = 0


                    # journ = self.env['account.journal'].search(
                    #     [('name', '=', 'Bank'), ('company_id', '=', datev.company_id.id)])
                    journ = self.journal_id

                    stmt = self.env['account.bank.statement'].create({'name': self.sub_partner.name,
                                                                      'balance_start': bal,
                                                                      # 'journal_id': line.journal_id.id,
                                                                      'journal_id': journ.id,
                                                                      'balance_end_real': bal+self.amount_total

                                                                      })

                if amount:
                    if datev.amount_total >= amount:
                        actual = amount

                        product_line = (0, 0, {
                            'date': self.payment_date,
                            'name': datev.display_name,
                            'partner_id': self.sub_partner.id,
                            'ref': datev.display_name,
                            'amount': amount
                        })
                        amount = amount - amount
                        payment_list.append(product_line)
                    else:
                        if datev.amount_total != 0:
                            amount = amount - datev.amount_total
                            actual = datev.amount_total
                            product_line = (0, 0, {
                                'date': self.payment_date,
                                'name': datev.display_name,
                                'partner_id': self.sub_partner.id,
                                'ref': datev.display_name,
                                'amount': datev.amount_total
                            })
                            payment_list.append(product_line)

                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
                    # journ = self.env['account.journal'].search(
                    #     [('name', '=', 'Bank'), ('company_id', '=', datev.company_id.id)])
                    journ = self.journal_id
                    pay_id = self.env['account.payment'].create({'partner_id': self.sub_partner.id,
                                                                 'amount': actual,
                                                                 'partner_type': self.partner_type,
                                                                 'company_id': datev.company_id.id,
                                                                 'payment_type': self.payment_type,
                                                                 'payment_method_id': self.payment_method_id.id,
                                                                 'journal_id': journ.id,
                                                                 'communication': type,
                                                                 'invoice_ids': [(6, 0, datev.ids)]
                                                                 })
                    pay_id.post()
                    pay_id.action_cash_book()
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)

            if stmt:
                stmt.line_ids = payment_list
                stmt.move_line_ids = pay_id_list
                stmt.write({'state': 'confirm'})
                self.write({'state': 'validate'})

                bal = sum(self.env['account.invoice'].search([('partner_id', '=', self.sub_partner.id)]).mapped(
                    'amount_total_signed'))
                if self.env['partner.ledger.customer'].search(
                    [('company_id', '=', account[0].company_id.id), ('partner_id', '=', self.sub_partner.id)]):
                    bal = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', account[0].company_id.id), ('partner_id', '=', self.sub_partner.id)])[-1].balance

                if not partner_led:
                    self.env['partner.ledger.customer'].sudo().create({
                        'date': datetime.today().date(),
                        # 'invoice_id': inv.id,
                        'description': type + '  ' + 'To' + '  ' + self.journal_id.company_id.name + ' ' + '& CO,' + 'A/C No:' + self.journal_id.default_debit_account_id.display_name + ' ' + 'on' + ' ' + str(
                            self.cleared_date),
                        'partner_id': self.sub_partner.id,
                        'company_id': datev.company_id.id,
                        'neft_id':self.id,
                        'credit': self.amount_total,
                        'balance': bal - self.amount_total,
                        # 'account_move':pay_id.move_line_ids.mapped('move_id')[0].id,
                        'account_journal': journ.id

                    })
            self.action_accountant_record()
        else:
            # vals = {
            #     'journal_id': self.journal_id.id,
            #     'state': 'draft',
            #     'ref': 'Cheque Payment'
            # }
            # pay_id_list = []
            # move_id = self.env['account.move'].create(vals)
            # label = 'Cheque Payment'
            #
            # temp = (0, 0, {
            #     'account_id': self.env['account.account'].sudo().search(
            #         [('name', '=', 'Creditors'),
            #          ('company_id', '=', self.journal_id.company_id.id)]).id,
            #     'name': label,
            #     'move_id': move_id.id,
            #     'date': self.payment_date,
            #     'partner_id': self.partner_id,
            #     'debit': self.amount_total,
            #     'credit': 0,
            # })
            # pay_id_list.append(temp)
            #
            # temp = (0, 0, {
            #     'account_id': self.from_account.id,
            #     'name': 'Credit Amount',
            #     'move_id': move_id.id,
            #     'date': self.payment_date,
            #     'partner_id': self.partner_id.id,
            #     'debit': 0,
            #     'credit': self.amount_total,
            # })
            # pay_id_list.append(temp)
            # move_id.line_ids = pay_id_list
            # move_id.action_post()
            stmt1 = self.env['account.bank.statement']
            if not stmt1:
                # bal = sum(self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped(
                #     'debit'))

                if self.env['account.bank.statement'].search([('company_id', '=', self.journal_id.company_id.id),
                                                              ('journal_id', '=', self.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', self.journal_id.company_id.id),
                         ('journal_id', '=', self.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                # journ = self.env['account.journal'].search(
                #     [('name', '=', 'Bank'), ('company_id', '=', datev.company_id.id)])
                journ = self.journal_id
                payment_list = []

                stmt1 = self.env['account.bank.statement'].create({'name': self.accountant.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': journ.id,
                                                                  'balance_end_real': bal - self.amount_total

                                                                  })

                product_line = (0, 0, {
                    'date': self.payment_date,
                    'name': self.display_name,
                    'partner_id': self.accountant.id,
                    'ref': self.name,
                    'amount': -self.amount_total
                })
                payment_list.append(product_line)
                journ = self.journal_id
                pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                                                             'amount': self.amount_total,
                                                              'partner_type': 'supplier',
                                                              'payment_type': 'outbound',
                                                             'company_id': self.journal_id.company_id.id,
                                                             'payment_method_id': self.payment_method_id.id,
                                                             'journal_id': journ.id,
                                                             'communication': self.cheque_no,
                                                             # 'invoice_ids': [(6, 0, datev.ids)]
                                                             })
                pay_id.post()
                pay_id.action_cash_book()
                pay_id_list = []
                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)

            if stmt1:
                stmt1.line_ids = payment_list
                stmt1.move_line_ids = pay_id_list
                stmt1.write({'state': 'confirm'})
                # self.write({'state': 'validate'})

            invoices = self.env['account.invoice'].search(
                [('partner_id', '=', self.accountant.id),
                 ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
            if invoices.mapped('residual'):
                balance_amount = sum(invoices.mapped('residual'))
            else:
                balance_amount = sum(invoices.mapped('amount_total'))

            Previous_led = self.env['supplier.ledger.customer'].search(
                [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)])
            if Previous_led:
                # balance_amount = Previous_led[-1].balance + line.price_subtotal_signed + self.amount_tax
                balance_amount = Previous_led[-1].balance - self.amount_total

            self.env['supplier.ledger.customer'].sudo().create({
                'date': datetime.today().date(),
                'partner_id': self.accountant.id,
                'description': self.cheque_no,
                # 'purchase_id': self.env['purchase.order'].search([('invoice_ids', '=', self.id)]).id or False,
                # 'invoice_id': self.id,
                'neft_id':self.id,
                'month': str(datetime.today().date().month),
                'company_id': self.env.user.company_id.id,
                # 'product_id': line.product_id.id,
                # 'price_units': line.quantity,
                # 'uom': line.product_id.uom_id.id,
                # 'rate': line.price_unit,
                # 'credit': line.price_subtotal_signed + self.amount_tax,
                'debit': self.amount_total,
                'balance': balance_amount

            })
            self.write({'state': 'validate'})

    def action_reverse(self):
        self.write({'state':'return'})
        if self.type != 'cheque':
            neft_ref_id = self.env['partner.ledger.customer'].sudo().search([('neft_id','=',self.id),('company_id','=',1),('partner_id','=',self.accountant.id)])
            if neft_ref_id:
                stmt = self.env['account.bank.statement']
                bal = sum(self.env['account.invoice'].search(
                    [('company_id', '=', 1), ('partner_id', '=', self.accountant.id)]).mapped('amount_total_signed'))

                if not stmt:
                    journ = self.env['account.journal'].search(
                        [('name', '=', 'Bank'), ('company_id', '=', 1)])

                    if self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                        bal = self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                            0].balance_end_real
                    else:
                        bal = 0

                    # if self.env['partner.ledger.customer'].search(
                    #     [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)]):
                    #     bal = self.env['partner.ledger.customer'].search(
                    #         [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)])[-1].balance

                    stmt = self.env['account.bank.statement'].create({'name': self.accountant.name,
                                                                      'balance_start': bal,
                                                                      # 'journal_id': line.journal_id.id,
                                                                      'journal_id': journ.id,
                                                                      'balance_end_real': bal - self.amount_total
                                                                      })

                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

                    # pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                    #                                              # 'amount': datev.amount_total,
                    #                                              'amount': self.amount_total,
                    #                                              'partner_type': self.partner_type,
                    #                                              'company_id': 1,
                    #                                              'payment_type': self.payment_type,
                    #                                              'payment_method_id': self.payment_method_id.id,
                    #                                              # 'journal_id': line.journal_id.id,
                    #                                              'journal_id': journ.id,
                    #                                              'communication': type + 'to ,from' + self.accountant.name + '=>' + journ.company_id.name + ',' + journ.name,
                    #
                    #                                              })

                    pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                                                                 'amount': self.amount_total,
                                                                 'partner_type': 'supplier',
                                                                 'payment_type': 'outbound',
                                                                 'payment_method_id': self.payment_method_id.id,
                                                                 'journal_id': journ.id,
                                                                 'communication': 'Reverse Entry',
                                                                 # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                                 })
                    pay_id.post()
                    if not self.env['cash.book.info'].search([]):
                        complete = sum(
                            self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped('debit'))
                    else:
                        complete = self.env['cash.book.info'].search([])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    type_m = 'outbound'
                    if self.journal_id.type == "cash":

                        self.env['cash.book.info'].create({
                            'date': self.payment_date,
                            'account_journal': self.journal_id.id,
                            'account': self.account_id.id,
                            'company_id': 1,
                            'description': self.name + ' ' + self.reference,
                            'payment_type': type_m,
                            # 'partner_type': self.partner_type,
                            'debit': debit,
                            'credit': self.amount_total,
                            # 'payment_id': self.id,
                            'balance': complete - self.amount_total

                        })
                    pay_id_list = []
                    payment_list = []
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)
                    product_line = (0, 0, {
                        'date': self.payment_date,
                        'name': self.type,
                        'partner_id': self.accountant.id,
                        'ref': self.type,
                        'amount': -self.amount_total})
                    payment_list.append(product_line)

                    Previous_led = self.env['partner.ledger.customer'].sudo().search(
                        [('company_id', '=', 1), ('partner_id', '=', self.accountant.id)])
                    if Previous_led:
                        balance_amount = Previous_led[-1].balance
                    else:
                        balance_amount = 0

                    self.env['partner.ledger.customer'].sudo().create({
                        'date': datetime.today().date(),
                        # 'invoice_id': inv.id,
                        'description': self.type +' ' + 'Reverse Entry' + ' ' + str(
                            self.cleared_date),
                        'partner_id': self.accountant.id,
                        'company_id': 1,
                        'check_only': True,
                        # 'neft_id': self.id,
                        'debit': self.amount_total,
                        'balance': balance_amount + self.amount_total,
                        'account_move': pay_id.move_line_ids.mapped('move_id')[0].id,
                        'account_journal': self.journal_id.id
                    })

                if stmt:
                    stmt.line_ids = payment_list
                    stmt.move_line_ids = pay_id_list
                    stmt.write({'state': 'confirm'})


            neft_ref_child = self.env['partner.ledger.customer'].sudo().search([('neft_id','=',self.id),('company_id','!=',1),('partner_id','=',self.sub_partner.id)])
            if neft_ref_child:
                stmt = self.env['account.bank.statement']
                # bal = sum(self.env['account.invoice'].search(
                #     [('company_id', '=', 1), ('partner_id', '=', self.sub_partner.id)]).mapped('amount_total_signed'))

                if not stmt:
                    journ = self.journal_id

                    if self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                        bal = self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                            0].balance_end_real
                    else:
                        bal = 0

                    # if self.env['partner.ledger.customer'].search(
                    #     [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)]):
                    #     bal = self.env['partner.ledger.customer'].search(
                    #         [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)])[-1].balance

                    stmt = self.env['account.bank.statement'].create({'name': self.sub_partner.name,
                                                                      'balance_start': bal,
                                                                      # 'journal_id': line.journal_id.id,
                                                                      'journal_id': journ.id,
                                                                      'balance_end_real': bal - self.amount_total
                                                                      })

                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
                    pay_id = self.env['account.payment'].create({'partner_id': self.sub_partner.id,
                                                                 'amount': self.amount_total,
                                                                 'partner_type': 'supplier',
                                                                 'payment_type': 'outbound',
                                                                 'payment_method_id': self.payment_method_id.id,
                                                                 'journal_id': journ.id,
                                                                 'communication': 'Reverse Entry',
                                                                 # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                                 })
                    pay_id.post()
                    if not self.env['cash.book.info'].search([]):
                        complete = sum(
                            self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped('debit'))
                    else:
                        complete = self.env['cash.book.info'].search([])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    type_m = 'outbound'
                    if self.journal_id.type == "cash":

                        self.env['cash.book.info'].create({
                            'date': self.payment_date,
                            'account_journal': self.journal_id.id,
                            'account': self.sub_partner.id,
                            'company_id': 1,
                            'description': self.name + ' ' + self.reference,
                            'payment_type': type_m,
                            # 'partner_type': self.partner_type,
                            'debit': debit,
                            'credit': self.amount_total,
                            # 'payment_id': self.id,
                            'balance': complete - self.amount_total

                        })
                    pay_id_list = []
                    payment_list = []
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)
                    product_line = (0, 0, {
                        'date': self.payment_date,
                        'name': self.type,
                        'partner_id': self.sub_partner.id,
                        'ref': self.type,
                        'amount': -self.amount_total})
                    payment_list.append(product_line)

                    Previous_led = self.env['partner.ledger.customer'].sudo().search(
                        [('company_id', '!=', 1), ('partner_id', '=', self.sub_partner.id)])
                    if Previous_led:
                        balance_amount = Previous_led[-1].balance
                        company_id = Previous_led[0].company_id.id
                    else:
                        balance_amount = 0
                        company_id = 1

                    self.env['partner.ledger.customer'].sudo().create({
                        'date': datetime.today().date(),
                        # 'invoice_id': inv.id,
                        'description': 'Return Entry ' + str(self.cleared_date),
                        'partner_id': self.sub_partner.id,
                        'company_id': company_id,
                        'check_only': True,
                        # 'neft_id': self.id,
                        'debit': self.amount_total,
                        'balance': balance_amount + self.amount_total,
                        'account_move': pay_id.move_line_ids.mapped('move_id')[0].id,
                        'account_journal': self.journal_id.id
                    })

                if stmt:
                    stmt.line_ids = payment_list
                    stmt.move_line_ids = pay_id_list
                    stmt.write({'state': 'confirm'})
        else:
            stmt1 = self.env['account.bank.statement']
            if not stmt1:
                # bal = sum(self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped(
                #     'debit'))

                if self.env['account.bank.statement'].search([('company_id', '=', self.journal_id.company_id.id),
                                                              ('journal_id', '=', self.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', self.journal_id.company_id.id),
                         ('journal_id', '=', self.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                # journ = self.env['account.journal'].search(
                #     [('name', '=', 'Bank'), ('company_id', '=', datev.company_id.id)])
                journ = self.journal_id
                payment_list = []

                stmt1 = self.env['account.bank.statement'].create({'name': self.accountant.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': journ.id,
                                                                  'balance_end_real': bal + self.amount_total

                                                                  })

                product_line = (0, 0, {
                    'date': self.payment_date,
                    'name': self.display_name,
                    'partner_id': self.accountant.id,
                    'ref': self.name,
                    'amount': -self.amount_total
                })
                payment_list.append(product_line)
                journ = self.journal_id
                # pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                #                                              'amount': self.amount_total,
                #                                               'partner_type': 'supplier',
                #                                               'payment_type': 'outbound',
                #                                              'company_id': self.journal_id.company_id.id,
                #                                              'payment_method_id': self.payment_method_id.id,
                #                                              'journal_id': journ.id,
                #                                              'communication': self.cheque_no,
                #                                              # 'invoice_ids': [(6, 0, datev.ids)]
                #                                              })
                pay_id = self.env['account.payment'].create({'partner_id': self.accountant.id,
                                                             'amount': self.amount_total,
                                                             'partner_type': 'customer',
                                                             'company_id': self.journal_id.company_id.id,
                                                             'payment_type': self.payment_type,
                                                             'payment_method_id': self.payment_method_id.id,
                                                             'journal_id': journ.id,
                                                             'communication': type,
                                                             # 'invoice_ids': [(6, 0, datev.ids)]
                                                             })
                pay_id.post()
                pay_id.action_cash_book()
                pay_id_list = []
                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)

            if stmt1:
                stmt1.line_ids = payment_list
                stmt1.move_line_ids = pay_id_list
                stmt1.write({'state': 'confirm'})
                # self.write({'state': 'validate'})

            invoices = self.env['account.invoice'].search(
                [('partner_id', '=', self.accountant.id),
                 ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
            if invoices.mapped('residual'):
                balance_amount = sum(invoices.mapped('residual'))
            else:
                balance_amount = sum(invoices.mapped('amount_total'))

            Previous_led = self.env['supplier.ledger.customer'].search(
                [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', self.accountant.id)])
            if Previous_led:
                # balance_amount = Previous_led[-1].balance + line.price_subtotal_signed + self.amount_tax
                balance_amount = Previous_led[-1].balance + self.amount_total

            self.env['supplier.ledger.customer'].sudo().create({
                'date': datetime.today().date(),
                'partner_id': self.accountant.id,
                'description': self.cheque_no,
                # 'purchase_id': self.env['purchase.order'].search([('invoice_ids', '=', self.id)]).id or False,
                # 'invoice_id': self.id,
                'neft_id':self.id,
                'month': str(datetime.today().date().month),
                'company_id': self.env.user.company_id.id,
                # 'product_id': line.product_id.id,
                # 'price_units': line.quantity,
                # 'uom': line.product_id.uom_id.id,
                # 'rate': line.price_unit,
                'credit': self.amount_total,
                'debit': 0,
                'balance': balance_amount

            })






class FreightDiscount(models.Model):
    _inherit = 'freight.disc'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('reverse', 'Reverse Entry'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', track_sequence=3,
        default='draft')


    def action_reverse(self):
        self.write({'state': 'reverse'})
        for line in self.freight_lines.filtered(lambda a:a.reverse == True):
            stmt = self.env['account.bank.statement']
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0].id
            if not stmt:
                if self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': line.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal-line.amount

                                                                  })

            payment_list = []
            pay_id_list = []
            account = self.env['account.invoice'].search(
                [('partner_id', '=', line.partner_id.id), ('state', '=', 'open')])

            # for check_inv in account:
            product_line = (0, 0, {
                'date': self.creates_date,
                # 'name': check_inv.display_name,
                'name': self.name,
                'partner_id': line.partner_id.id,
                'ref': self.name,
                'amount': -line.amount
            })

            payment_list.append(product_line)

            pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'supplier',
                                                         'payment_type': 'outbound',
                                                         'payment_method_id': j,
                                                         'journal_id': line.journal_id.id,
                                                         'communication': 'Reverse Entry',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })

            pay_id.post()
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)
            if line.journal_id.type == 'cash':
                if not self.env['cash.book.info'].search([]):
                    complete = sum(
                        self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                            'debit'))
                else:
                    complete = self.env['cash.book.info'].search([])[-1].balance

                debit = 0
                credit = line.amount
                complete_new = 0
                acc = self.env['account.account']
                # if self.payment_type == 'outbound':
                debit = 0
                # complete_new = complete - credit
                complete_new = complete - credit
                acc = line.journal_id.default_credit_account_id.id
                # if self.payment_type == 'inbound':
                #     debit = self.amount
                #     complete_new = complete + debit
                #     acc = self.journal_id.default_debit_account_id.id

                self.env['cash.book.info'].create({
                    'date': datetime.today().date(),
                    'account_journal': line.journal_id.id,
                    'partner_id': line.partner_id.id,
                    'company_id': 1,
                    # 'description': self.communication,
                    'description': line.partner_id.name,
                    'payment_type': 'outbound',
                    'partner_type': 'supplier',
                    'debit': debit,
                    'credit': credit,
                    'account': acc,
                    # 'payment_id': self.id,
                    'balance': complete_new

                })
            invoices = self.env['account.invoice'].search(
                [('partner_id', '=', line.partner_id.id), ('company_id', '=', self.company_id.id),
                 ('state', '!=', 'paid')])
            if invoices.mapped('residual'):
                balance_amount = sum(invoices.mapped('residual'))
            else:
                balance_amount = sum(invoices.mapped('amount_total'))
            balance_amount += self.env['partner.ledger.customer'].search(
                [('partner_id', '=', line.partner_id.id), ('description', '=', 'Opening Balance')]).balance
            preview = self.env['partner.ledger.customer'].search(
                [('company_id', '=', self.company_id.id), ('partner_id', '=', line.partner_id.id)])
            if preview:
                balance_amount = self.env['partner.ledger.customer'].search(
                    [('company_id', '=', self.company_id.id), ('partner_id', '=', line.partner_id.id)])[-1].balance
            self.env['partner.ledger.customer'].sudo().create({
                'date': datetime.today().date(),
                'description': line.freight.name,
                'partner_id': line.partner_id.id,
                'company_id': self.company_id.id,
                'account_journal': line.journal_id.id,
                'account_move': pay_id.move_line_ids.mapped('move_id').id,
                'debit': line.amount,
                'credit': 0,
                'balance': balance_amount + line.amount,
            })
            if stmt:
                stmt.line_ids = payment_list
                stmt.move_line_ids = pay_id_list
                stmt.write({'state': 'confirm'})








class FreightDiscountLines(models.Model):
    _inherit = 'freight.disc.lines'

    reverse = fields.Boolean(string='Reverse')


class ExpensesDiscount(models.Model):
    _inherit = 'expenses.disc'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('reverse', 'Reverse Entry'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', track_sequence=3,
        default='draft')

    def action_reverse(self):
        self.write({'state': 'reverse'})
        for line in self.freight_lines.filtered(lambda a:a.reverse == True):
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0].id

            stmt = self.env['account.bank.statement']
            payment_list = []
            if not stmt:
                # _get_payment_info_JSON
                # bal = sum(
                #     self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                #         'debit'))
                # bal = self.env['account.bank.statement'].search([('journal_id', '=', line.journal_id.id)]).balance_end_real

                if self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                  'balance_start': bal,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal+line.amount

                                                                  })
            payment_list = []
            product_line = (0, 0, {
                'date': self.creates_date,
                'name': self.name,
                'partner_id': line.journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': line.amount
            })
            payment_list.append(product_line)
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
            journal = line.journal_id
            pay_id = self.env['account.payment'].create({'partner_id': journal.company_id.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'customer',
                                                          'payment_type': 'inbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': journal.id,
                                                         'communication': 'Reverse Entry',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })
            pay_id.post()
            pay_id_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)

            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
            if line.journal_id.type == 'cash' and line.journal_id.company_id.id == 1:
                if not self.env['cash.book.info'].search([]):
                    complete = sum(
                        self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                            'debit'))
                else:
                    complete = self.env['cash.book.info'].search([])[-1].balance

                debit = 0
                credit = 0
                complete_new = 0
                acc = self.env['account.account']
                # if self.payment_type == 'outbound':
                # credit = line.amount
                debit = line.amount
                complete_new = complete + debit
                acc = line.journal_id.default_credit_account_id.id
                self.env['cash.book.info'].create({
                    'date': datetime.today().date(),
                    'account_journal': line.journal_id.id,
                    # 'partner_id': line.partner_id.id,
                    'company_id': 1,
                    # 'description': self.communication,
                    'description': line.reason,
                    'payment_type': 'outbound',
                    'partner_type': 'customer',
                    'debit': debit,
                    'credit': credit,
                    'account': acc,
                    # 'payment_id': self.id,
                    'balance': complete_new

                })

class ExpensesDiscounttLines(models.Model):
    _inherit = 'expense.disc.lines'

    reverse = fields.Boolean(string='Reverse')



class InternalAmountTransfer(models.Model):
    _inherit = 'internal.amount.transfer'
    _order = 'id desc'


    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('reverse', 'Reverse Entry'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', track_sequence=3,
        default='draft')

    def action_post(self):
        self.write({'state': 'done'})
        for line in self.freight_lines:
            self.env['bank.transfer.lines'].create({
                'date': datetime.today().date(),
                'freight_ids': self.id,
                'reason': line.reason,
                'amount': line.amount,
                'from_acc_company': line.from_acc_company.id,
                'to_acc_company': line.to_acc_company.id,
                'journal_id': line.journal_id.id,
                'account_id': line.account_id.id,
                'to_account': line.to_account.id,
                'balance': line.balance,
                'to_balance': line.to_balance
            })

            # j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0].id
            # vals = {
            #     'journal_id': line.journal_id.id,
            #     'state': 'draft',
            #     'ref': self.name
            # }
            # pay_id_list = []
            # move_id = self.env['account.move'].create(vals)
            # label = self.name
            # temp = (0, 0, {
            #     # 'account_id': acc.id,
            #     'account_id': line.account_id.id,
            #     'name': label,
            #     'move_id': move_id.id,
            #     'date': datetime.today().date(),
            #     # 'partner_id': line.partner_id.id,
            #     'debit': 0,
            #     'credit': line.amount,
            # })
            # pay_id_list.append(temp)
            # temp = (0, 0, {
            #     'account_id': line.to_account.id,
            #     'name': label,
            #     'move_id': move_id.id,
            #     'date': datetime.today().date(),
            #     'debit': line.amount,
            #     'credit': 0,
            # })
            # pay_id_list.append(temp)
            #
            # move_id.line_ids = pay_id_list
            # move_id.action_post()
            ###above last meeting wwithout stmt$$$$$$$$$$4
            stmt = self.env['account.bank.statement']
            payment_list = []
            if not stmt:
                # _get_payment_info_JSON
                # bal = sum(
                #     self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                #         'debit'))
                # bal = self.env['account.bank.statement'].search([('journal_id', '=', line.journal_id.id)]).balance_end_real

                if self.env['account.bank.statement'].search([('company_id', '=', line.journal_id.company_id.id),
                                                              ('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.journal_id.company_id.id),
                         ('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                  'balance_start': bal,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal - line.amount

                                                                  })

            product_line = (0, 0, {
                'date': self.create_date,
                'name': self.name,
                'partner_id': line.journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': -line.amount
            })
            payment_list.append(product_line)
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
            journal = line.journal_id
            pay_id = self.env['account.payment'].create({'partner_id': journal.company_id.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'supplier',
                                                         'payment_type': 'outbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': journal.id,
                                                         'communication': 'Fund Transfer',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })
            pay_id.post()
            pay_id_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)

            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
            self.bank_receiver(line)
            complete = 0
            if line.journal_id.type == 'cash':
                if not self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
                    acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.account_id.id)])
                    complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                    acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                    complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))

                else:
                    if self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
                        complete = self.env['cash.book.info'].search([('account', '=', line.account_id.id)])[-1].balance
                    if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        complete_sub = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[
                            -1].balance

                debit = 0
                credit = 0
                complete_new = 0
                # acc = self.env['account.account']
                # if self.payment_type == 'outbound':
                # credit = self.amount
                # complete_new = complete - credit
                # acc = line.journal_id.default_credit_account_id.id
                # if self.payment_type == 'inbound':
                #     debit = self.amount
                #     complete_new = complete + debit
                #     acc = self.journal_id.default_debit_account_id.id
                complete_new = complete
                self.env['cash.book.info'].create({
                    'date': datetime.today().date(),
                    'account_journal': line.journal_id.id,
                    # 'partner_id': line.partner_id.id,
                    'company_id': 1,
                    # 'description': self.communication,
                    'description': self.name,
                    'payment_type': 'outbound',
                    'partner_type': 'customer',
                    'debit': 0,
                    'credit': line.amount,
                    'account': line.account_id.id,
                    # 'payment_id': self.id,
                    'balance': complete_new - line.amount

                })
                # if line.to_account.
                # self.env['cash.book.info'].create({
                #     'date': datetime.today().date(),
                #     'account_journal': line.journal_id.id,
                #     'partner_id': line.partner_id.id,
                #     'company_id': 1,
                #     # 'description': self.communication,
                #     'description': self.name,
                #     'payment_type': 'outbound',
                #     'partner_type': 'customer',
                #     'debit': line.amount,
                #     'credit': 0,
                #     'account': line.to_account.id,
                #     # 'payment_id': self.id,
                #     'balance': complete_sub
                #
                # })
            if line.journal_id.type == 'bank':
                if line.to_account.name == 'Cash' and line.to_account.company_id.id == 1:
                    if not self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                        complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                        acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                        complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))

                    else:
                        if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                            complete = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[
                                -1].balance
                        # if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        #    complete_sub = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    journal_id = self.env['account.journal'].search(
                        [('name', '=', 'Cash'), ('company_id', '=', self.env.user.company_id.id)])
                    complete_new = complete
                    self.env['cash.book.info'].create({
                        'date': datetime.today().date(),
                        'account_journal': journal_id.id,
                        # 'partner_id': line.partner_id.id,
                        'company_id': 1,
                        # 'description': self.communication,
                        'description': self.name,
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'debit': line.amount,
                        'credit': 0,
                        'account': line.to_account.id,
                        # 'payment_id': self.id,
                        'balance': complete_new+line.amount

                    })

    def bank_receiver(self, line):
        for line in line:
            stmt = self.env['account.bank.statement']
            payment_list = []
            if not stmt:
                if self.env['account.bank.statement'].search([('company_id', '=', line.to_journal_id.company_id.id),
                                                              ('journal_id', '=', line.to_journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.to_journal_id.company_id.id),
                         ('journal_id', '=', line.to_journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                  'balance_start': bal,
                                                                  'journal_id': line.to_journal_id.id,
                                                                  'balance_end_real': bal + line.amount

                                                                  })

            product_line = (0, 0, {
                'date': self.create_date,
                'name': self.name,
                'partner_id': line.to_journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': line.amount
            })
            payment_list.append(product_line)
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
            journal = line.to_journal_id
            pay_id = self.env['account.payment'].create({'partner_id': journal.company_id.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'customer',
                                                         'payment_type': 'inbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': journal.id,
                                                         'communication': 'Fund Receiver',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })
            pay_id.post()
            pay_id_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)

            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})

    def action_reverse(self):
        self.write({'state': 'reverse'})
        for line in self.freight_lines.filtered(lambda a:a.reverse == True):
            self.env['bank.transfer.lines'].create({
                'date': datetime.today().date(),
                'freight_ids': self.id,
                'reason': line.reason,
                'amount': line.amount,
                'from_acc_company': line.from_acc_company.id,
                'to_acc_company': line.to_acc_company.id,
                'journal_id': line.journal_id.id,
                'account_id': line.account_id.id,
                'to_account': line.to_account.id,
                'balance': line.balance,
                'to_balance': line.to_balance
            })
            stmt = self.env['account.bank.statement']
            payment_list = []
            if not stmt:
                if self.env['account.bank.statement'].search([('company_id', '=', line.journal_id.company_id.id),
                                                              ('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.journal_id.company_id.id),
                         ('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                  'balance_start': bal,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal + line.amount

                                                                  })

            product_line = (0, 0, {
                'date': self.create_date,
                'name': self.name,
                'partner_id': line.journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': line.amount
            })
            payment_list.append(product_line)
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
            journal = line.journal_id
            pay_id = self.env['account.payment'].create({'partner_id': journal.company_id.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'customer',
                                                         'payment_type': 'inbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': journal.id,
                                                         'communication': 'Reverse Entry',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })
            pay_id.post()
            pay_id_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)

            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
            self.bank_rev_receiver(line)
            complete = 0
            if line.journal_id.type == 'cash':
                if not self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
                    acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.account_id.id)])
                    complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                    acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                    complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))

                else:
                    if self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
                        complete = self.env['cash.book.info'].search([('account', '=', line.account_id.id)])[-1].balance
                    if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        complete_sub = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[
                            -1].balance

                debit = 0
                credit = 0
                complete_new = 0
                # acc = self.env['account.account']
                # if self.payment_type == 'outbound':
                # credit = self.amount
                # complete_new = complete - credit
                # acc = line.journal_id.default_credit_account_id.id
                # if self.payment_type == 'inbound':
                #     debit = self.amount
                #     complete_new = complete + debit
                #     acc = self.journal_id.default_debit_account_id.id
                complete_new = complete
                self.env['cash.book.info'].create({
                    'date': datetime.today().date(),
                    'account_journal': line.journal_id.id,
                    # 'partner_id': line.partner_id.id,
                    'company_id': 1,
                    # 'description': self.communication,
                    'description': 'Reverse'+''+self.name,
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'debit': line.amount,
                    'credit': 0,
                    'account': line.account_id.id,
                    # 'payment_id': self.id,
                    'balance': complete_new + line.amount

                })
            if line.journal_id.type == 'bank':
                if line.to_account.name == 'Cash' and line.to_account.company_id.id == 1:
                    if not self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                        complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                        acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                        complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))

                    else:
                        if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                            complete = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[
                                -1].balance
                        # if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
                        #    complete_sub = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    journal_id = self.env['account.journal'].search(
                        [('name', '=', 'Cash'), ('company_id', '=', self.env.user.company_id.id)])
                    complete_new = complete
                    self.env['cash.book.info'].create({
                        'date': datetime.today().date(),
                        'account_journal': journal_id.id,
                        # 'partner_id': line.partner_id.id,
                        'company_id': 1,
                        # 'description': self.communication,
                        'description': self.name,
                        'payment_type': 'outbound',
                        'partner_type': 'supplier',
                        'debit': 0,
                        'credit': line.amount,
                        'account': line.to_account.id,
                        # 'payment_id': self.id,
                        'balance': complete_new - line.amount

                    })

    def bank_rev_receiver(self, line):
        for line in line:
            stmt = self.env['account.bank.statement']
            payment_list = []
            if not stmt:
                if self.env['account.bank.statement'].search([('company_id', '=', line.to_journal_id.company_id.id),
                                                              ('journal_id', '=', line.to_journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.to_journal_id.company_id.id),
                         ('journal_id', '=', line.to_journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                  'balance_start': bal,
                                                                  'journal_id': line.to_journal_id.id,
                                                                  'balance_end_real': bal - line.amount

                                                                  })

            product_line = (0, 0, {
                'date': self.create_date,
                'name': self.name,
                'partner_id': line.to_journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': -line.amount
            })
            payment_list.append(product_line)
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
            journal = line.to_journal_id
            pay_id = self.env['account.payment'].create({'partner_id': journal.company_id.partner_id.id,
                                                         'amount': line.amount,
                                                         'partner_type': 'supplier',
                                                         'payment_type': 'outbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': journal.id,
                                                         'communication': 'Reverse Entry',
                                                         # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                         })
            pay_id.post()
            pay_id_list = []
            for k in pay_id.move_line_ids:
                pay_id_list.append(k.id)

            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
            # if line.to_journal_id.type == 'cash':
            #     if not self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
            #         acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.account_id.id)])
            #         complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
            #         acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
            #         complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
            #
            #     else:
            #         if self.env['cash.book.info'].search([('account', '=', line.account_id.id)]):
            #             complete = self.env['cash.book.info'].search([('account', '=', line.account_id.id)])[-1].balance
            #         if self.env['cash.book.info'].search([('account', '=', line.to_account.id)]):
            #             complete_sub = self.env['cash.book.info'].search([('account', '=', line.to_account.id)])[
            #                 -1].balance
            #
            #     debit = 0
            #     credit = 0
            #     complete_new = 0
            #     # acc = self.env['account.account']
            #     # if self.payment_type == 'outbound':
            #     # credit = self.amount
            #     # complete_new = complete - credit
            #     # acc = line.journal_id.default_credit_account_id.id
            #     # if self.payment_type == 'inbound':
            #     #     debit = self.amount
            #     #     complete_new = complete + debit
            #     #     acc = self.journal_id.default_debit_account_id.id
            #     complete_new = complete
            #     self.env['cash.book.info'].create({
            #         'date': datetime.today().date(),
            #         'account_journal': line.journal_id.id,
            #         # 'partner_id': line.partner_id.id,
            #         'company_id': 1,
            #         # 'description': self.communication,
            #         'description': 'Reverse'+''+self.name,
            #          'payment_type': 'outbound',
            #         'partner_type': 'supplier',
            #         'debit':0 ,
            #         'credit': line.amount,
            #         'account': line.account_id.id,
            #         # 'payment_id': self.id,
            #         'balance': complete_new - line.amount
            #
            #     })



class InternalTransferLines(models.Model):
    _inherit = 'internal.transfer.lines'

    reverse = fields.Boolean(string='Reverse')



    @api.multi
    def compute_balance(self):
        for each in self:
            if each.account_id:
                # self.journal_id  = self.env['account.journal'].search([('name', '=', 'Bank'), ('company_id', '=', self.account_id.company_id.id)])
                complete = 0
                if each.journal_id.type == 'cash':

                    if not self.env['cash.book.info'].search([('account', '=', each.account_id.id)]):
                        # complete = sum(self.env['account.move.line'].search(
                        #     [('company_id', '=', self.env.user.company_id.id),
                        #      ('account_id', '=', self.account_id.id)]).mapped(
                        #     'debit'))
                        if self.env['account.bank.statement'].search([('company_id', '=', each.journal_id.company_id.id),
                                                                      ('journal_id', '=', each.journal_id.id)]):
                            complete = self.env['account.bank.statement'].search(
                                [('company_id', '=', each.journal_id.company_id.id),
                                 ('journal_id', '=', each.journal_id.id)])[0].balance_end_real
                        else:
                            complete = 0

                    else:
                        if self.env['cash.book.info'].search([('account', '=', each.account_id.id)]):
                            complete = self.env['cash.book.info'].search([])[-1].balance
                    each.balance = complete

                else:

                    # acc = self.env['account.move.line'].sudo().search([('account_id', '=', self.account_id.id)])
                    # bal = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                    if self.env['account.bank.statement'].search([('journal_id', '=', each.journal_id.id)]):
                        bal = self.env['account.bank.statement'].search([('journal_id', '=', each.journal_id.id)])[
                            0].balance_end_real
                    else:
                        bal = 0
                    each.balance = bal

    @api.depends('to_account')
    def compute_to_balance(self):
        for each in self:
            if each.to_account:
                if self.env['cash.book.info'].search([('account', '=', each.to_account.id)]):
                    each.to_balance = self.env['cash.book.info'].search([])[-1].balance
                else:
                    # acc = self.env['account.move.line'].sudo().search([('account_id', '=', self.to_account.id)])
                    # self.to_balance = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                    if self.env['account.bank.statement'].search([('company_id', '=', each.to_journal_id.company_id.id),
                                                                  ('journal_id', '=', each.to_journal_id.id)]):
                        bal = self.env['account.bank.statement'].search(
                            [('company_id', '=', each.to_journal_id.company_id.id),
                             ('journal_id', '=', each.to_journal_id.id)])[
                            0].balance_end_real
                    else:
                        bal = 0
                    each.to_balance = bal

class AmountWithdraw(models.Model):
    _inherit = "amount.withdraw"

    state = fields.Selection([('draft', 'Draft'),('reverse', 'Reverse Entry'), ('done', 'Done'), ('cancelled', 'Cancelled')], readonly=True, default='draft', copy=False, string="Status")


    def action_reverse(self):
        self.write({'state': 'reverse'})
        if self.type_of_draw == 'withdraw':

            pay_id_list = []
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

            pay_id = self.env['account.payment'].create({'partner_id': self.journal_id.company_id.partner_id.id,
                                                         'amount': self.amount,
                                                         'partner_type': 'customer',
                                                          'payment_type': 'inbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': self.journal_id.id,
                                                         'communication':self.reference,
                                                         })
        else:
            pay_id_list = []
            j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

            pay_id = self.env['account.payment'].create({'partner_id': self.journal_id.company_id.partner_id.id,
                                                         'amount': self.amount,
                                                         'partner_type': 'supplier',
                                                         'payment_type': 'outbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': self.journal_id.id,
                                                         'communication': self.reference,
                                                         })

        pay_id.post()
        for k in pay_id.move_line_ids:
            pay_id_list.append(k.id)

        stmt = self.env['account.bank.statement']
        if not stmt:
            journ = self.journal_id
            # bal = sum(self.env['account.move.line'].search([('journal_id', '=', journ.id)]).mapped(
            #     'debit'))

            if self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                bal = self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                    0].balance_end_real
            else:
                bal = 0
            if self.type_of_draw == 'withdraw':
                stmt = self.env['account.bank.statement'].create({'name': self.journal_id.company_id.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': self.journal_id.id,
                                                                  'balance_end_real': bal + self.amount

                                                                  })
                payment_list = []
                product_line = (0, 0, {
                    'date': self.payment_date,
                    # 'name': check_inv.display_name,
                    'name': self.name,
                    'partner_id': self.journal_id.company_id.partner_id.id,
                    'ref': self.name,
                    'amount': self.amount
                })

                payment_list.append(product_line)
            else:
                stmt = self.env['account.bank.statement'].create({'name': self.journal_id.company_id.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': self.journal_id.id,
                                                                  'balance_end_real': bal - self.amount

                                                                  })
                payment_list = []
                product_line = (0, 0, {
                    'date': self.payment_date,
                    # 'name': check_inv.display_name,
                    'name': self.name,
                    'partner_id': self.journal_id.company_id.partner_id.id,
                    'ref': self.name,
                    'amount': -self.amount
                })

                payment_list.append(product_line)

        # move_id.action_cash_book()
        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
        self.receiver_entry_side()
        if self.type == 'cash' and self.journal_id.type == 'cash':
            # complete = sum(self.env['account.move.line'].search([('journal_id', '=', acc.id)]).mapped('debit'))
            # complete = sum(self.env['account.move.line'].search(
            #     [('company_id', '=', self.env.user.company_id.id), ('account_id', '=', acc.id)]).mapped('debit'))
            if not self.env['cash.book.info'].search([]):

                if self.env['account.bank.statement'].search([('journal_id', '=', self.journal_id.id)]):
                    complete = self.env['account.bank.statement'].search([('journal_id', '=', self.journal_id.id)])[
                        0].balance_end_real
                else:
                    complete = 0

                # complete = sum(
                #     self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped('debit'))
            else:
                complete = self.env['cash.book.info'].search([])[-1].balance

            debit = 0
            credit = 0
            complete_new = 0
            if self.type_of_draw == 'withdraw':
                debit = self.amount
                complete_new = complete + debit
                acc = self.journal_id.default_debit_account_id
            else:
                credit = self.amount
                complete_new = complete - credit
                acc = self.journal_id.default_debit_account_id
            type_m = ''
            if self.type_of_draw == 'withdraw':
                type_m = 'outbound'
            if self.type_of_draw == 'deposit':
                type_m = 'inbound'

            self.env['cash.book.info'].create({
                'date': self.payment_date,
                'account_journal': self.journal_id.id,
                'account': acc.id,
                'partner_id': self.partner_id.id,
                'company_id': 1,
                'description': 'Reverse Entry' + ' ' + self.reference,
                'payment_type': type_m,

                # 'partner_type': self.partner_type,
                'debit': debit,
                'credit': credit,
                # 'payment_id': self.id,
                'balance': complete_new

            })
    def receiver_entry_side(self):

        pay_id_list = []
        j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
        if self.type_of_draw == 'withdraw':


            pay_id = self.env['account.payment'].create({'partner_id': self.to_journal_id.company_id.partner_id.id,
                                                         'amount': self.amount,
                                                         'partner_type': 'supplier',
                                                          'payment_type': 'outbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': self.to_journal_id.id,
                                                         'communication': ' Cash Received',
                                                         })
        else:
            pay_id = self.env['account.payment'].create({'partner_id': self.to_journal_id.company_id.partner_id.id,
                                                         'amount': self.amount,
                                                         'partner_type': 'supplier',
                                                          'payment_type': 'outbound',
                                                         'payment_method_id': j.id,
                                                         'journal_id': self.to_journal_id.id,
                                                         'communication': 'Reverse Entry Cash withdraw',
                                                         })


        pay_id.post()
        for k in pay_id.move_line_ids:
            pay_id_list.append(k.id)

        stmt = self.env['account.bank.statement']
        if not stmt:
            journ = self.to_journal_id
            # bal = sum(self.env['account.move.line'].search([('journal_id', '=', journ.id)]).mapped(
            #     'debit'))

            if self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                bal = self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                    0].balance_end_real
            else:
                bal = 0
            if self.type_of_draw == 'withdraw':

                stmt = self.env['account.bank.statement'].create({'name': self.to_journal_id.company_id.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': self.to_journal_id.id,
                                                                  'balance_end_real': bal - self.amount

                                                                  })
                payment_list = []
                product_line = (0, 0, {
                    'date': self.payment_date,
                    # 'name': check_inv.display_name,
                    'name': self.name,
                    'partner_id': self.to_journal_id.company_id.partner_id.id,
                    'ref': self.name,
                    'amount': -self.amount
                })

                payment_list.append(product_line)
            else:
                stmt = self.env['account.bank.statement'].create({'name': self.to_journal_id.company_id.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': self.to_journal_id.id,
                                                                  'balance_end_real': bal + self.amount

                                                                  })
                payment_list = []
                product_line = (0, 0, {
                    'date': self.payment_date,
                    # 'name': check_inv.display_name,
                    'name': self.name,
                    'partner_id': self.to_journal_id.company_id.partner_id.id,
                    'ref': self.name,
                    'amount': self.amount
                })

                payment_list.append(product_line)

        # move_id.action_cash_book()
        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})


class CashToBank(models.Model):
    _inherit = 'cash.to.bank'

    state = fields.Selection([('draft', 'Draft'),('reverse', 'Reverse Entry'), ('done', 'Done'), ('cancelled', 'Cancelled')], readonly=True,
                             default='draft', copy=False, string="Status")

    def action_reverse(self):
        self.write({'state': 'reverse'})
        pay_id_list = []
        j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

        pay_id = self.env['account.payment'].create({'partner_id': self.journal_id.company_id.partner_id.id,
                                                     'amount': self.amount,
                                                     'partner_type': 'customer',
                                                     'payment_type': 'inbound',
                                                     'payment_method_id': j.id,
                                                     'journal_id': self.journal_id.id,
                                                     'communication': 'Reverse Entry Cash Transfer',
                                                     })
        pay_id.post()
        for k in pay_id.move_line_ids:
            pay_id_list.append(k.id)

        stmt = self.env['account.bank.statement']
        if not stmt:
            journ = self.journal_id
            if self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                bal = self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                    0].balance_end_real
            else:
                bal = 0
            stmt = self.env['account.bank.statement'].create({'name': self.journal_id.company_id.partner_id.name,
                                                              'balance_start': bal,
                                                              # 'journal_id': line.journal_id.id,
                                                              'journal_id': self.journal_id.id,
                                                              'balance_end_real': bal + self.amount

                                                              })
            payment_list = []
            product_line = (0, 0, {
                'date': self.payment_date,
                # 'name': check_inv.display_name,
                'name': self.name,
                'partner_id': self.journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': self.amount
            })

            payment_list.append(product_line)

        # move_id.action_cash_book()
        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})

        self.receiver_entry_side()

        if self:
            # complete = sum(self.env['account.move.line'].search([('journal_id', '=', acc.id)]).mapped('debit'))
            complete = sum(self.env['account.move.line'].search(
                [('company_id', '=', self.env.user.company_id.id), ('account_id', '=', self.account_id.id)]).mapped(
                'debit'))
            if not self.env['cash.book.info'].search([]):
                complete = sum(
                    self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped('debit'))
            else:
                complete = self.env['cash.book.info'].search([])[-1].balance

            debit = 0
            credit = 0
            complete_new = 0
            type_m = 'inbound'

            self.env['cash.book.info'].create({
                'date': self.payment_date,
                'account_journal': self.journal_id.id,
                'account': self.account_id.id,
                # 'partner_id': self.partner_id.id,
                'company_id': 1,
                'description': 'Reverse' + ' ' + self.reference,
                'payment_type': type_m,
                # 'partner_type': self.partner_type,
                'debit': self.amount,
                'credit': debit,
                # 'payment_id': self.id,
                'balance': complete + self.amount

            })

    def receiver_entry_side(self):

        pay_id_list = []
        j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

        pay_id = self.env['account.payment'].create({'partner_id': self.to_journal_id.company_id.partner_id.id,
                                                     'amount': self.amount,
                                                     'partner_type': 'supplier',
                                                     'payment_type': 'outbound',
                                                     'payment_method_id': j.id,
                                                     'journal_id': self.to_journal_id.id,
                                                     'communication': 'Reverse Entry Cash Received',
                                                     })
        pay_id.post()
        for k in pay_id.move_line_ids:
            pay_id_list.append(k.id)

        stmt = self.env['account.bank.statement']
        if not stmt:
            journ = self.to_journal_id
            if self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                bal = self.env['account.bank.statement'].search(
                    [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                    0].balance_end_real
            else:
                bal = 0
            stmt = self.env['account.bank.statement'].create({'name': self.to_journal_id.company_id.partner_id.name,
                                                              'balance_start': bal,
                                                              # 'journal_id': line.journal_id.id,
                                                              'journal_id': self.to_journal_id.id,
                                                              'balance_end_real': bal - self.amount

                                                              })
            payment_list = []
            product_line = (0, 0, {
                'date': self.payment_date,
                # 'name': check_inv.display_name,
                'name': self.name,
                'partner_id': self.to_journal_id.company_id.partner_id.id,
                'ref': self.name,
                'amount': -self.amount
            })

            payment_list.append(product_line)

        # move_id.action_cash_book()
        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})


class CashierDirectCollection(models.Model):
    _inherit = "cashier.direct.collection"

    state = fields.Selection([('draft', 'Draft'), ('validate', 'Validate'),('reverse', 'Reverse Entry'),  ('cancelled', 'Cancelled')], readonly=True,
                             default='draft', copy=False, string="Status")

    def action_reverse(self):
        self.write({'state':'reverse'})
        for line in self.partner_invoices.filtered(lambda a:a.reverse == True):
            if line.partner_id:
                cv = 0

                stmt = self.env['account.bank.statement']
                if not stmt:
                    journ = line.journal_id
                    if self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                        bal = self.env['account.bank.statement'].search(
                            [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                            0].balance_end_real
                    else:
                        bal = 0
                    stmt = self.env['account.bank.statement'].create({'name': line.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal - line.amount_total

                                                                  })
                    payment_list = []
                    product_line = (0, 0, {
                        'date': self.payment_date,
                        # 'name': check_inv.display_name,
                        'name': self.name,
                        'partner_id': line.partner_id.id,
                        'ref': self.name,
                        'amount': -line.amount_total
                    })

                    payment_list.append(product_line)

                    pay_id_list = []


                journal = self.env['account.journal'].search(
                    [('name', '=', 'Cash'), ('company_id', '=', self.env.user.company_id.id)])
                j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

                pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                             'amount': line.amount_total,
                                                             'partner_type': 'supplier',
                                                             'payment_type': 'outbound',
                                                             'payment_method_id': j.id,
                                                             'journal_id': journal.id,
                                                             'communication': 'Reverse Entry Direct Cash Collection',
                                                             })
                pay_id.post()
                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)

                pay_id.action_cash_book()

                invoices = self.env['account.invoice'].search(
                    [('partner_id', '=', line.partner_id.id), ('company_id', '=', self.env.user.company_id.id),
                     ('state', '!=', 'paid')])
                if invoices.mapped('residual'):
                    balance_amount = sum(invoices.mapped('residual'))
                else:
                    balance_amount = sum(invoices.mapped('amount_total'))
                balance_amount += self.env['partner.ledger.customer'].search(
                    [('partner_id', '=', self.env.user.company_id.id), ('description', '=', 'Opening Balance')]).balance

                preveious = self.env['partner.ledger.customer'].search(
                    [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])
                if preveious:
                    balance_amount = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])[-1].balance

                self.env['partner.ledger.customer'].sudo().create({
                    'date': datetime.today().date(),
                    'description': 'Reverse Entry Direct Collection',
                    'partner_id': line.partner_id.id,
                    'company_id': self.env.user.company_id.id,
                    'account_journal': journal.id,
                    'credit': 0,
                    'debit': line.amount_total,
                    'balance': balance_amount + line.amount_total,
                })
                if stmt:
                    stmt.line_ids = payment_list
                    stmt.move_line_ids = pay_id_list
                    stmt.write({'state': 'confirm'})


            else:
                if line.journal_id.company_id == self.env.user.company_id:
                    pay_id_list = []
                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

                    pay_id = self.env['account.payment'].create({'partner_id': line.journal_id.company_id.partner_id.id,
                                                                 'amount': line.amount_total,
                                                                 'partner_type': 'supplier',
                                                                 'payment_type': 'outbound',
                                                                 'payment_method_id': j.id,
                                                                 'journal_id': line.journal_id.id,
                                                                 'communication': 'Return Direct Cash Collection',
                                                                 })
                    pay_id.post()
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)

                    stmt = self.env['account.bank.statement']
                    if not stmt:
                        journ = line.journal_id
                        if self.env['account.bank.statement'].search(
                                [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)]):
                            bal = self.env['account.bank.statement'].search(
                                [('company_id', '=', journ.company_id.id), ('journal_id', '=', journ.id)])[
                                0].balance_end_real
                        else:
                            bal = 0
                        stmt = self.env['account.bank.statement'].create({'name': line.journal_id.company_id.partner_id.name,
                                                                          'balance_start': bal,
                                                                          # 'journal_id': line.journal_id.id,
                                                                          'journal_id': line.journal_id.id,
                                                                          'balance_end_real': bal - line.amount_total

                                                                          })
                        payment_list = []
                        product_line = (0, 0, {
                            'date': self.payment_date,
                            # 'name': check_inv.display_name,
                            'name': self.name,
                            'partner_id': line.journal_id.company_id.partner_id.id,
                            'ref': self.name,
                            'amount': -line.amount_total
                        })

                        payment_list.append(product_line)
                    # complete = sum(self.env['account.move.line'].search(
                    #     [('company_id', '=', self.env.user.company_id.id),
                    #      ('account_id', '=', line.journal_id.default_debit_account_id.id)]).mapped(
                    #     'debit'))
                    # if not self.env['cash.book.info'].search([]):
                    #     complete = sum(
                    #         self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped('debit'))
                    # else:
                    #     complete = self.env['cash.book.info'].search([])[-1].balance

                    if not self.env['cash.book.info'].search([]):

                        if self.env['account.bank.statement'].search(
                                [('company_id', '=', line.journal_id.company_id.id),
                                 ('journal_id', '=', line.journal_id.id)]):
                            complete = self.env['account.bank.statement'].search(
                                [('company_id', '=', line.journal_id.company_id.id),
                                 ('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                        else:
                            complete = 0
                    else:
                        complete = self.env['cash.book.info'].search([])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    type_m = 'outbound'

                    self.env['cash.book.info'].create({
                        'date': self.payment_date,
                        'account_journal': line.journal_id.id,
                        'account': line.journal_id.default_debit_account_id.id,
                        # 'partner_id': self.partner_id.id,
                        'company_id': 1,
                        'description': line.reason,
                        'payment_type': type_m,
                        # 'partner_type': self.partner_type,
                        'debit':0 ,
                        'credit': line.amount_total,
                        'balance': complete - line.amount_total

                    })
                if stmt:
                    stmt.line_ids = payment_list
                    stmt.move_line_ids = pay_id_list
                    stmt.write({'state': 'confirm'})


class CashierDirectCollectionLines(models.Model):
    _inherit = "cashier.direct.collection.line"

    reverse = fields.Boolean(string='Reverse')

class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_reverse_cash_book(self):
        if self.journal_id.type == 'cash':
            if not self.env['cash.book.info'].search([]):
                # complete = sum(self.env['account.move.line'].search([('journal_id', '=', self.journal_id.id)]).mapped('debit'))
                complete = sum(self.env['account.move.line'].search(
                    [('account_id', '=', self.journal_id.default_credit_account_id.id)]).mapped('debit'))
            else:
                complete = self.env['cash.book.info'].search([])[-1].balance

            debit = 0
            credit = 0
            complete_new = 0
            acc = self.env['account.account']
            if self.payment_type == 'outbound':
                credit = self.amount
                complete_new = complete + credit
                acc = self.journal_id.default_credit_account_id.id
            if self.payment_type == 'inbound':
                debit = self.amount
                complete_new = complete - debit
                acc = self.journal_id.default_debit_account_id.id

            self.env['cash.book.info'].create({
                'date': self.payment_date,
                'account_journal': self.journal_id.id,
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
                # 'description': self.communication,
                'description': self.partner_id.name,
                'payment_type': self.payment_type,
                'partner_type': self.partner_type,
                'debit': debit,
                'credit': credit,
                'account': acc,
                'payment_id': self.id,
                'balance': complete_new

            })

class FundTransferBTCompanies(models.Model):
    _inherit = "fund.transfer.companies"

    state = fields.Selection([
        ('draft', 'Draft'),
        ('send', 'Send'),
        ('reverse', 'Reverse Entry'),
        ('received', 'Received'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, track_visibility='onchange', track_sequence=3,
        default='draft')


    def action_reverse(self):
        self.write({'state': 'reverse'})
        # self.sudo().receiver_fund()
        receive  = self.env['fund.receiver.companies'].search([('fund_id','=',self.id),('state','=','draft')])
        if receive:
            receive.write({'state':'cancel'})
            for line in self.fund_lines.filtered(lambda a:a.reverse == True):
                stmt = self.env['account.bank.statement']
                payment_list = []
                if not stmt:
                    if self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)]):
                        bal = self.env['account.bank.statement'].search([('company_id','=',line.journal_id.company_id.id),('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                    else:
                        bal = 0

                    stmt = self.env['account.bank.statement'].create({'name': self.name,
                                                                      'balance_start': bal,
                                                                      'journal_id': line.journal_id.id,
                                                                      'balance_end_real': bal+line.amount

                                                                      })

                product_line = (0, 0, {
                    'date': self.create_date,
                    'name': self.name,
                    'partner_id': line.journal_id.company_id.partner_id.id,
                    'ref': self.name,
                    'amount': line.amount
                })
                payment_list.append(product_line)
                j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
                journal = line.journal_id
                pay_id = self.env['account.payment'].create({'partner_id': self.company_id.partner_id.id,
                                                             'amount': line.amount,
                                                             'partner_type': 'customer',
                                                             'payment_type': 'inbound',
                                                             'payment_method_id': j.id,
                                                             'journal_id': journal.id,
                                                             'communication': 'Fund Transfer',
                                                             # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                             })
                pay_id.post()
                pay_id_list = []
                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)

                stmt.line_ids = payment_list
                stmt.move_line_ids = pay_id_list
                stmt.write({'state': 'confirm'})
                if line.journal_id.type == 'cash':
                    if not self.env['cash.book.info'].sudo().search([('account', '=', line.account_id.id)]):
                        acc = self.env['account.move.line'].sudo().search([('account_id', '=', line.account_id.id)])
                        complete = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))
                        acc_sub = self.env['account.move.line'].sudo().search([('account_id', '=', line.to_account.id)])
                        complete_sub = sum(acc.mapped('debit')) - sum(acc.mapped('credit'))

                    else:
                        complete = self.env['cash.book.info'].sudo().search([('account', '=', line.account_id.id)])[-1].balance
                        # complete_sub = self.env['cash.book.info'].sudo().search([('account', '=', line.to_account.id)])[-1].balance

                    debit = 0
                    credit = 0
                    complete_new = 0
                    complete_new = complete
                    self.env['cash.book.info'].sudo().create({
                        'date': datetime.today().date(),
                        'account_journal': line.sudo().journal_id.id,
                        # 'partner_id': line.partner_id.id,
                        'company_id': 1,
                        # 'description': self.communication,
                        'description': self.name,
                        'payment_type': 'inbound',
                        'partner_type': 'customer',
                        'debit': line.amount,
                        'credit': 0,
                        'account': line.sudo().account_id.id,
                        # 'payment_id': self.id,
                        'balance': complete_new+line.amount

                    })

        else:
            raise ValidationError(_('You Can Reverse the Entries if other side company Record in Draft state Only'))




class FundTransferBTCompaniesLines(models.Model):
    _inherit = "transfer.companies.line"

    reverse = fields.Boolean(string='Reverse')


class CompanyExpensesReport(models.Model):
    _name = "company.expenses.report"

    name = fields.Char("Name", index=True, default=lambda self: _('New'))
    sequence = fields.Integer(index=True)
    payment_date = fields.Date(string='Create Date', default=fields.Date.context_today, required=True, copy=False)
    from_date = fields.Date(string='From Date', copy=False, default=fields.Date.context_today, )
    to_date = fields.Date(string='To Date', copy=False, default=fields.Date.context_today, )
    report_lines = fields.One2many('sale.report.custom.line', 'report_line')
    # partner_id = fields.Many2one('res.partner', string='Party Wise')
    description = fields.Char(string="Description")
    company_id = fields.Many2one('res.company', string='Company', index=True,
                                 default=lambda self: self.env.user.company_id)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            if 'company_id' in vals:
                vals['name'] = self.env['ir.sequence'].with_context(force_company=vals['company_id']).next_by_code(
                    'company.expenses.report') or _('New')
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('company.expenses.report') or _('New')
        return super(CompanyExpensesReport, self).create(vals)

    # def print_report(self):
    #     if self.description:
    #         total_ledgers = self.env['expenses.disc.lines'].search(
    #             [('date', '>=', self.from_date), ('date', '<=', self.to_date),
    #              ('description', '=', self.description)])
    #     else:
    #         total_ledgers = self.env['expenses.disc.lines'].search(
    #             [('date', '>=', self.from_date), ('date', '<=', self.to_date), ('description', '=', self.description)])
    #     action_vals = {
    #         'name': self.description,
    #         'domain': [('id', 'in', total_ledgers.ids)],
    #         'view_type': 'form',
    #         'res_model': 'partner.ledger.customer',
    #         'view_id': False,
    #         'type': 'ir.actions.act_window',
    #     }
    #     if len(total_ledgers) == 1:
    #         action_vals.update({'res_id': total_ledgers[0].id, 'view_mode': 'form'})
    #     else:
    #         action_vals['view_mode'] = 'tree,form'
    #     return action_vals

    @api.multi
    def print_reports(self):
        return self.env.ref('enz_multi_updations.expenses_ledger_reports').report_action(self)

    def print_all(self):
        if self.description:
            total_ledgers_parent = self.env['expenses.disc'].search(
                [('creates_date', '>=', self.from_date), ('creates_date', '<=', self.to_date),
                 ])
            total_ledgers = total_ledgers_parent.mapped('freight_lines').search([('reason', '=', self.description)])
            return total_ledgers

        else:
            total_ledgers_parent = self.env['expenses.disc'].search(
                [('creates_date', '>=', self.from_date), ('creates_date', '<=', self.to_date)])
            total_ledgers = total_ledgers_parent.mapped('freight_lines')
            return total_ledgers
