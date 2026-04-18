frappe.listview_settings["Purisol Coupon Booklet"] = {
	onload(listview) {
		if (!frappe.user.has_role("Purisol Administrator")) {
			return;
		}

		listview.page.add_action_item(__("Sell Selected to Customer"), function () {
			const selected = listview.get_checked_items();

			if (!selected.length) {
				frappe.msgprint(__("Please select at least one booklet."));
				return;
			}

			for (const row of selected) {
				if (!["In Stock", "In Custody"].includes(row.status)) {
					frappe.msgprint(
						__(
							"Only booklets with status 'In Stock' or 'In Custody' can be sold. '{0}' has status '{1}'.",
							[row.name, row.status]
						)
					);
					return;
				}
			}

			const selected_names = selected.map((r) => r.name);
			const booklet_list_html = selected_names.map((n) => `<li>${n}</li>`).join("");

			frappe.prompt(
				[
					{
						fieldname: "customer",
						label: __("Customer"),
						fieldtype: "Link",
						options: "Customer",
						reqd: 1,
					},
					{
						fieldname: "price_list",
						label: __("Price List"),
						fieldtype: "Link",
						options: "Price List",
						description: __("Leave blank to use Customer default or Settings default."),
					},
					{
						fieldname: "booklets_info",
						label: __("Selected Booklets"),
						fieldtype: "HTML",
						options: `<ul>${booklet_list_html}</ul>`,
						read_only: 1,
					},
				],
				function (values) {
					frappe.call({
						method: "cx_purisol.cx_purisol.api.sell_booklets.purisol_create_sales_invoice_for_booklets",
						args: {
							customer: values.customer,
							booklets: selected_names,
							price_list: values.price_list || null,
						},
						callback: function (r) {
							if (r.message && r.message.name) {
								frappe.set_route("Form", "Sales Invoice", r.message.name);
							}
						},
					});
				},
				__("Sell Selected to Customer"),
				__("Sell")
			);
		});
	},
};
