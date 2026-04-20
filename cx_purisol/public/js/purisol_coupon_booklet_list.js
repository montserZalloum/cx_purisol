frappe.listview_settings["Purisol Coupon Booklet"] = {
	onload(listview) {
		if (!frappe.user.has_role("Purisol Administrator")) {
			return;
		}

		// Generate Booklets - always visible as inner button
		listview.page.add_inner_button(__("Generate Booklets"), function() {
			const d = new frappe.ui.Dialog({
				title: __("Generate Booklets"),
				fields: [
					{
						label: __("Quantity"),
						fieldname: "quantity",
						fieldtype: "Int",
						reqd: 1,
						description: __("Number of booklets to generate (≤ 20 runs inline; > 20 runs in background)"),
					},
					{
						label: __("Batch ID"),
						fieldname: "batch_id",
						fieldtype: "Data",
						description: __("Optional identifier to tag this generation batch"),
					},
				],
				primary_action_label: __("Generate"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "cx_purisol.cx_purisol.api.booklet_generation.purisol_generate_booklets",
						args: { quantity: values.quantity, batch_id: values.batch_id || null },
						callback(r) {
							if (!r.exc) {
								const data = r.message;
								if (data.mode === "sync") {
									frappe.msgprint({
										title: __("Booklets Generated"),
										message: __(
											"Created {0} booklets ({1} → {2}) and {3} coupons.",
											[values.quantity, data.first_booklet, data.last_booklet, data.total_coupons]
										),
										indicator: "green",
									});
									listview.refresh();
								} else {
									frappe.show_alert({
										message: __("Generating {0} booklets in background…", [values.quantity]),
										indicator: "blue",
									});
									_subscribe_progress(data.job_name, listview);
								}
							}
						},
					});
				},
			});
			d.show();
		});

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

function _subscribe_progress(job_name, listview) {
	frappe.realtime.on("purisol_generate_booklets_progress", (data) => {
		if (data.status === "progress") {
			frappe.show_alert({
				message: __("Generating… {0}/{1} booklets", [data.done, data.total]),
				indicator: "blue",
			});
		} else if (data.status === "complete") {
			frappe.realtime.off("purisol_generate_booklets_progress");
			frappe.msgprint({
				title: __("Booklets Generated"),
				message: __(
					"Created {0} booklets ({1} → {2}) and {3} coupons.",
					[data.total, data.first_booklet, data.last_booklet, data.total_coupons]
				),
				indicator: "green",
			});
			listview.refresh();
		} else if (data.status === "failed") {
			frappe.realtime.off("purisol_generate_booklets_progress");
			frappe.msgprint({
				title: __("Generation Failed"),
				message: data.error || __("An error occurred during booklet generation."),
				indicator: "red",
			});
		}
	});
}
