frappe.ui.form.on("Purisol Coupon Discrepancy", {
	refresh(frm) {
		_toggle_liable_delivery_man(frm);
		_render_related_men_banner(frm);
	},

	resolution_action(frm) {
		_toggle_liable_delivery_man(frm);
	},
});

function _toggle_liable_delivery_man(frm) {
	const action = frm.doc.resolution_action;
	const needs_person =
		action === "Add to Liability Ledger" || action === "Immediate Cash Payment";
	frm.set_df_property("liable_delivery_man", "hidden", needs_person ? 0 : 1);
	frm.set_df_property("liable_delivery_man", "reqd", needs_person ? 1 : 0);
}

async function _render_related_men_banner(frm) {
	if (
		!frm.doc.related_delivery_men ||
		!frm.doc.related_delivery_men.length ||
		frm.__related_men_banner
	) return;

	const rows = frm.doc.related_delivery_men;
	const ids = [...new Set(rows.map(r => r.delivery_man).filter(Boolean))];
	const name_by_id = {};
	if (ids.length) {
		const employees = await frappe.db.get_list("Employee", {
			filters: { name: ["in", ids] },
			fields: ["name", "employee_name"],
			limit: ids.length,
		});
		for (const e of employees) {
			name_by_id[e.name] = e.employee_name || e.name;
		}
	}

	const items = rows.map(r => {
		const display = name_by_id[r.delivery_man] || r.delivery_man;
		let link = "";
		if (r.custody_entry) {
			link = `<a href="/app/purisol-custody-entry/${r.custody_entry}" target="_blank">${r.custody_entry}</a>`;
		} else if (r.consumption_entry) {
			link = `<a href="/app/purisol-coupon-consumption-entry/${r.consumption_entry}" target="_blank">${r.consumption_entry}</a>`;
		}
		return `<li><strong>${frappe.utils.escape_html(display)}</strong> — ${__(r.role)}${link ? " — " + link : ""}</li>`;
	}).join("");

	const html = `<div class="alert alert-info" style="margin:8px 0">
		<strong>${__("Related Delivery Men")}</strong>
		<ul style="margin:4px 0 0 16px">${items}</ul>
	</div>`;

	const $banner = $(html);
	frm.layout.wrapper.find(".form-page").prepend($banner);
	frm.__related_men_banner = $banner;
}
