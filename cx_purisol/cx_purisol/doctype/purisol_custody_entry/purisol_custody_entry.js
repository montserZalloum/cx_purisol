frappe.ui.form.on("Purisol Custody Entry", {
	refresh(frm) {
		_apply_entry_type_ux(frm);
	},

	entry_type(frm) {
		_apply_entry_type_ux(frm);
	},

	from_delivery_man(frm) {
		if (frm.doc.entry_type === "Transfer") {
			_apply_transfer_ux(frm);
		} else if (frm.doc.entry_type === "Return") {
			_apply_return_ux(frm);
		}
	},
});

function _apply_entry_type_ux(frm) {
	_set_booklet_filter(frm, null);

	const type = frm.doc.entry_type;
	if (type === "Assign") {
		_apply_assign_ux(frm);
	} else if (type === "Transfer") {
		_apply_transfer_ux(frm);
	} else if (type === "Return") {
		_apply_return_ux(frm);
	}
}

function _set_booklet_filter(frm, filters) {
	frm.fields_dict.booklets.grid.get_field("booklet").get_query = function () {
		return { filters: filters || {} };
	};
}

function _apply_assign_ux(frm) {
	frm.set_df_property("from_delivery_man", "hidden", 1);
	frm.set_df_property("from_delivery_man", "reqd", 0);
	frm.set_df_property("to_delivery_man", "hidden", 0);
	frm.set_df_property("to_delivery_man", "reqd", 1);
	_set_booklet_filter(frm, { status: "In Stock" });
}

function _apply_transfer_ux(frm) {
	frm.set_df_property("from_delivery_man", "hidden", 0);
	frm.set_df_property("from_delivery_man", "reqd", 1);
	frm.set_df_property("to_delivery_man", "hidden", 0);
	frm.set_df_property("to_delivery_man", "reqd", 1);
	const filters = frm.doc.from_delivery_man
		? { status: "In Custody", current_delivery_man: frm.doc.from_delivery_man }
		: { status: "In Custody" };
	_set_booklet_filter(frm, filters);
}

function _apply_return_ux(frm) {
	frm.set_df_property("from_delivery_man", "hidden", 0);
	frm.set_df_property("from_delivery_man", "reqd", 1);
	frm.set_df_property("to_delivery_man", "hidden", 1);
	frm.set_df_property("to_delivery_man", "reqd", 0);
	const filters = frm.doc.from_delivery_man
		? { status: "In Custody", current_delivery_man: frm.doc.from_delivery_man }
		: { status: "In Custody" };
	_set_booklet_filter(frm, filters);
}
