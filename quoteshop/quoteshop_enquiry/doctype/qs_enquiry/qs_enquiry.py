# Copyright (c) 2026, Abhijeet Shakya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

COUNTED_AVAILABILITY = ("Available", "Partial", "Not Available")
PRICED_STATUSES = ("Price Sent", "Accepted")


class QSEnquiry(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from quoteshop.quoteshop_enquiry.doctype.qs_enquiry_answer.qs_enquiry_answer import QSEnquiryAnswer
		from quoteshop.quoteshop_enquiry.doctype.qs_enquiry_item.qs_enquiry_item import QSEnquiryItem
		from quoteshop.quoteshop_enquiry.doctype.qs_enquiry_message.qs_enquiry_message import QSEnquiryMessage
		from quoteshop.quoteshop_enquiry.doctype.qs_enquiry_version.qs_enquiry_version import QSEnquiryVersion

		answers: DF.Table[QSEnquiryAnswer]
		assigned_to: DF.Link | None
		available_count: DF.Int
		business_name: DF.Data | None
		buyer_name: DF.Data
		buyer_type: DF.Data | None
		contact: DF.Link | None
		crm_deal: DF.Link | None
		current_version: DF.Int
		customer: DF.Link | None
		email: DF.Data | None
		items: DF.Table[QSEnquiryItem]
		line_count: DF.Int
		lost_reason: DF.SmallText | None
		messages: DF.Table[QSEnquiryMessage]
		mobile: DF.Data
		not_available_count: DF.Int
		notes: DF.SmallText | None
		partial_count: DF.Int
		pincode: DF.Data | None
		sales_order: DF.Link | None
		saved_pct: DF.Percent
		status: DF.Literal[
			"Draft", "Requested", "Price Sent", "Changes Requested", "Accepted", "Lost", "Expired"
		]
		total_listed: DF.Currency
		total_offered: DF.Currency
		total_saved: DF.Currency
		unit_count: DF.Float
		valid_till: DF.Date | None
		versions: DF.Table[QSEnquiryVersion]
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_not_accepted()
		self.set_totals()

	def validate_not_accepted(self) -> None:
		if (before := self.get_doc_before_save()) and before.status == "Accepted":
			frappe.throw(_("Enquiry {0} is accepted and can no longer be changed.").format(self.name))

	def set_totals(self) -> None:
		"""Line amounts, totals and counts in one pass over the items (CONTRACTS §6.1)."""
		amount_precision = self.precision("amount", "items")
		seen: set[str] = set()
		listed = offered = units = 0.0
		lines = 0
		counts = dict.fromkeys(COUNTED_AVAILABILITY, 0)
		priced = self.status in PRICED_STATUSES

		for row in self.items:
			if row.item_code in seen:
				frappe.throw(
					_("Row #{0}: Item {1} is already in this enquiry.").format(
						row.idx, frappe.bold(row.item_code)
					)
				)
			seen.add(row.item_code)

			row.offered_qty = flt(row.requested_qty if row.offered_qty is None else row.offered_qty)
			row.offered_rate = flt(row.listed_rate if row.offered_rate is None else row.offered_rate)
			removed = row.change_flag == "Removed"
			counted = not removed and row.availability != "Not Available"
			if priced and counted and row.offered_qty > 0 and row.offered_rate <= 0:
				frappe.throw(
					_("Row #{0}: Offered rate for {1} must be greater than 0.").format(
						row.idx, frappe.bold(row.item_code)
					)
				)
			row.amount = flt(row.offered_rate * row.offered_qty, amount_precision) if counted else 0.0

			if not removed:
				lines += 1
				if row.availability in counts:
					counts[row.availability] += 1
			if counted:
				listed += flt(row.listed_rate) * row.offered_qty
				offered += row.amount
				units += row.offered_qty

		self.total_listed = flt(listed, self.precision("total_listed"))
		self.total_offered = flt(offered, self.precision("total_offered"))
		self.total_saved = flt(self.total_listed - self.total_offered, self.precision("total_saved"))
		self.saved_pct = flt(self.total_saved / self.total_listed * 100, 2) if self.total_listed else 0.0
		self.line_count = lines
		self.unit_count = flt(units, self.precision("unit_count"))
		self.available_count = counts["Available"]
		self.partial_count = counts["Partial"]
		self.not_available_count = counts["Not Available"]
