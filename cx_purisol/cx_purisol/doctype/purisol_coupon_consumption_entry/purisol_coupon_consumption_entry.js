frappe.ui.form.on("Purisol Coupon Consumption Entry", {
	refresh(frm) {
		// T050: Post-submit modal for detected discrepancies (US6, contracts §6)
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.has_warnings === 1 &&
			frm.doc.discrepancies_detected &&
			frm.doc.discrepancies_detected.length > 0 &&
			!frm.__discrepancy_modal_shown
		) {
			const rows = frm.doc.discrepancies_detected;
			const fetches = rows.map(row =>
				frappe.db.get_value(
					"Purisol Coupon Discrepancy",
					row.discrepancy,
					["discrepancy_type", "booklet"]
				).then(r => ({ name: row.discrepancy, ...r.message }))
			);
			Promise.all(fetches).then(items => {
				const html = "<ul>" + items.map(d =>
					`<li><a href="/app/purisol-coupon-discrepancy/${d.name}" target="_blank">${d.name}</a>` +
					` — ${d.discrepancy_type || ""} — ${d.booklet || ""}</li>`
				).join("") + "</ul>";
				frappe.msgprint({
					title: __("Discrepancies detected"),
					message: html,
					indicator: "orange",
					wide: true,
				});
			});
			frm.__discrepancy_modal_shown = true;
		}

		if (frm.doc.docstatus !== 0) return;

		if (!frm._mode_section) {
			_build_mode_section(frm);
		}
	},
});

function _build_mode_section(frm) {
	const $wrapper = frm.get_field("notes").$wrapper.closest(".form-section").before(
		$(`<div class="purisol-mode-section" style="padding:12px 15px 0"></div>`)
	);
	const $section = frm.fields_dict["notes"].$wrapper.closest("form")
		.find(".purisol-mode-section");

	// Mode switcher
	const $switcher = $(`
		<div class="btn-group" role="group" style="margin-bottom:12px">
			<button class="btn btn-sm btn-primary mode-btn" data-mode="A">${__("By Booklet (Mode A)")}</button>
			<button class="btn btn-sm btn-default mode-btn" data-mode="B">${__("By Coupon Number (Mode B)")}</button>
		</div>
	`).appendTo($section);

	// Mode A panel
	const $modeA = $(`
		<div class="mode-a-panel">
			<div class="form-group">
				<label class="control-label">${__("Booklet")}</label>
				<div class="booklet-link-wrapper"></div>
			</div>
			<div class="coupon-checklist" style="margin:8px 0;max-height:300px;overflow-y:auto;border:1px solid #d1d8dd;border-radius:4px;padding:8px"></div>
			<button class="btn btn-sm btn-success add-to-entry-btn" style="margin-top:8px" disabled>
				${__("Add to Entry")}
			</button>
		</div>
	`).appendTo($section);

	// Mode B panel
	const $modeB = $(`
		<div class="mode-b-panel" style="display:none">
			<div class="form-group">
				<label class="control-label">${__("Coupon Numbers (one per line)")}</label>
				<textarea class="form-control coupon-numbers-input" rows="4"
					placeholder="${__("Type or paste coupon numbers, one per line…")}"></textarea>
			</div>
			<div style="margin-bottom:8px">
				<button class="btn btn-sm btn-default mode-b-resolve-btn">${__("Resolve & Add")}</button>
			</div>
			<div class="mode-b-results"></div>
		</div>
	`).appendTo($section);

	function _commit_mode_b() {
		const raw = $modeB.find(".coupon-numbers-input").val() || "";
		const lines = raw.split("\n").map(s => s.trim()).filter(Boolean);
		if (!lines.length) return;

		frappe.call({
			method: "cx_purisol.cx_purisol.api.consumption.resolve_coupons",
			args: { coupon_numbers: lines },
			callback(r) {
				const { resolved, unresolved } = r.message || { resolved: [], unresolved: [] };
				resolved.forEach(function (row) {
					frm.add_child("coupons", { coupon: row.coupon, booklet: row.booklet, customer: row.customer });
				});
				if (resolved.length) frm.refresh_field("coupons");

				const $results = $modeB.find(".mode-b-results").empty();
				unresolved.forEach(function (n) {
					$results.append(
						`<div class="text-danger" style="padding:2px 0">${__("Not found: {0}", [n])}</div>`
					);
				});

				if (!unresolved.length) {
					$modeB.find(".coupon-numbers-input").val("");
				}
			},
		});
	}

	$modeB.find(".coupon-numbers-input").on("keydown", function (e) {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			_commit_mode_b();
		}
	});

	$modeB.find(".mode-b-resolve-btn").on("click", _commit_mode_b);

	frm._mode_section = $section;

	// Booklet link field
	let booklet_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			options: "Purisol Coupon Booklet",
			fieldname: "booklet_picker",
			label: __("Booklet"),
			placeholder: __("Select a booklet…"),
		},
		parent: $modeA.find(".booklet-link-wrapper"),
		render_input: true,
	});
	booklet_control.refresh();

	let $checklist = $modeA.find(".coupon-checklist");
	let $addBtn = $modeA.find(".add-to-entry-btn");
	let available_coupons = [];

	booklet_control.$input.on("change", function () {
		const booklet = booklet_control.get_value();
		$checklist.empty();
		available_coupons = [];
		$addBtn.prop("disabled", true);

		if (!booklet) return;

		frappe.call({
			method: "cx_purisol.cx_purisol.api.consumption.list_available_coupons",
			args: { booklet },
			callback(r) {
				available_coupons = r.message || [];
				if (!available_coupons.length) {
					$checklist.html(`<div class="text-muted" style="padding:4px">${__("No available coupons in this booklet.")}</div>`);
					return;
				}
				available_coupons.forEach(function (c) {
					$checklist.append(`
						<label style="display:block;padding:2px 4px;cursor:pointer">
							<input type="checkbox" class="coupon-tick" data-coupon="${c.coupon}" style="margin-right:6px">
							${c.coupon} <span class="text-muted">(${__("Page")} ${c.page_number})</span>
						</label>
					`);
				});
				$addBtn.prop("disabled", false);
			},
		});
	});

	$addBtn.on("click", function () {
		const ticked = $checklist.find(".coupon-tick:checked");
		if (!ticked.length) {
			frappe.msgprint(__("Please tick at least one coupon."));
			return;
		}
		ticked.each(function () {
			frm.add_child("coupons", { coupon: $(this).data("coupon") });
		});
		frm.refresh_field("coupons");
		$checklist.find(".coupon-tick:checked").prop("checked", false);
	});

	// Mode switcher handler
	$switcher.on("click", ".mode-btn", function () {
		const mode = $(this).data("mode");
		$switcher.find(".mode-btn").removeClass("btn-primary").addClass("btn-default");
		$(this).removeClass("btn-default").addClass("btn-primary");
		$modeA.toggle(mode === "A");
		$section.find(".mode-b-panel").toggle(mode === "B");
	});
}
