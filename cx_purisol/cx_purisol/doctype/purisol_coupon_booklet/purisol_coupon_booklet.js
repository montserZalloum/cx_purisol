frappe.listview_settings["Purisol Coupon Booklet"] = {
	onload(listview) {
		listview.page.add_action_item(__("Generate Booklets"), () => {
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
