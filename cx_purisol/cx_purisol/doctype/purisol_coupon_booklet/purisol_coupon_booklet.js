frappe.ui.form.on("Purisol Coupon Booklet", {
	refresh(frm) {
		frm.set_df_property("status", "read_only", 1);
		frm.set_df_property("current_delivery_man", "read_only", 1);
	},
});
