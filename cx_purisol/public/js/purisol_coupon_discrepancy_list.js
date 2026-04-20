frappe.listview_settings["Purisol Coupon Discrepancy"] = {
	onload(listview) {
		if (listview.filter_area.get().length === 0) {
			listview.filter_area.add([
				["Purisol Coupon Discrepancy", "status", "=", "Open"],
			]);
		}
	},
};
