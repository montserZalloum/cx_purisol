frappe.listview_settings["Purisol Coupon Discrepancy"] = {
	onload(listview) {
		if (listview.filter_area.is_empty()) {
			listview.filter_area.add([
				["Purisol Coupon Discrepancy", "status", "=", "Open"],
			]);
		}
	},
};
