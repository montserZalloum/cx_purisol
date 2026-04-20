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
	coupons_add(frm) {
		if (frm.__sync_checklist) frm.__sync_checklist();
	},
	coupons_remove(frm) {
		setTimeout(() => {
			if (frm.__sync_checklist) frm.__sync_checklist();
		}, 0);
	},
});

function _build_mode_section(frm) {
	const $section = $(`<div class="purisol-mode-section" style="padding:12px 15px 0"></div>`);
	$(frm.wrapper).find('[data-fieldname="section_break_coupons"]').before($section);

	// Mode switcher
	const $switcher = $(`
		<div class="btn-group" role="group" style="margin-bottom:12px">
			<button type="button" class="btn btn-sm btn-primary mode-btn" data-mode="A">${__("By Booklet (Mode A)")}</button>
			<button type="button" class="btn btn-sm btn-default mode-btn" data-mode="B">${__("By Coupon Number (Mode B)")}</button>
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
			<button type="button" class="btn btn-sm btn-success add-to-entry-btn" style="margin-top:8px" disabled>
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
					placeholder="${__("Type or paste coupon numbers (e.g. CP-00001), one per line…")}"></textarea>
			</div>
			<div style="margin-bottom:8px">
				<button type="button" class="btn btn-sm btn-default mode-b-resolve-btn">${__("Resolve & Add")}</button>
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
				const consumable = resolved.filter(row => row.status !== "Consumed");
				const already_consumed = resolved.filter(row => row.status === "Consumed");
				if (consumable.length) _prune_empty_coupons();
				const existing = new Set((frm.doc.coupons || []).map(row => row.coupon));
				const duplicates = [];
				let added = 0;
				consumable.forEach(function (row) {
					if (existing.has(row.coupon)) {
						duplicates.push(row.coupon);
						return;
					}
					frm.add_child("coupons", { coupon: row.coupon, booklet: row.booklet, customer: row.customer });
					existing.add(row.coupon);
					added++;
				});
				if (added) frm.refresh_field("coupons");

				const $results = $modeB.find(".mode-b-results").empty();
				unresolved.forEach(function (n) {
					$results.append(
						`<div class="text-danger" style="padding:2px 0">${__("Not found: {0}", [n])}</div>`
					);
				});
				already_consumed.forEach(function (row) {
					$results.append(
						`<div class="text-danger" style="padding:2px 0">${__("Already consumed: {0}", [row.coupon])}</div>`
					);
				});
				duplicates.forEach(function (n) {
					$results.append(
						`<div class="text-warning" style="padding:2px 0">${__("Already added: {0}", [n])}</div>`
					);
				});

				if (!unresolved.length && !already_consumed.length) {
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

	let $checklist = $modeA.find(".coupon-checklist");
	let $addBtn = $modeA.find(".add-to-entry-btn");
	let available_coupons = [];
	let selected_booklet = null;
	let selected_customer = null;
	let _request_token = 0;

	function _prune_empty_coupons() {
		const rows = frm.doc.coupons || [];
		let removed = 0;
		for (let i = rows.length - 1; i >= 0; i--) {
			if (!rows[i].coupon) {
				frappe.model.clear_doc(rows[i].doctype, rows[i].name);
				removed++;
			}
		}
		return removed;
	}

	function _sync_checklist() {
		const current = new Set((frm.doc.coupons || []).map(row => row.coupon));
		$checklist.find(".coupon-tick").each(function () {
			const $cb = $(this);
			const added = current.has($cb.data("coupon"));
			$cb.prop("disabled", added).prop("checked", added);
			const $label = $cb.closest("label");
			$label.css({
				cursor: added ? "default" : "pointer",
				opacity: added ? 0.85 : 1,
			});
			$label.find(".coupon-remove-btn").toggle(added);
		});
	}
	frm.__sync_checklist = _sync_checklist;

	function _on_booklet_change() {
		const booklet = booklet_control.get_value() || null;

		if (booklet === selected_booklet) return;

		const my_token = ++_request_token;
		selected_booklet = booklet;
		selected_customer = null;
		available_coupons = [];
		$checklist.empty();
		$addBtn.prop("disabled", true);

		if (!booklet) return;

		frappe.db.get_value("Purisol Coupon Booklet", booklet, "customer").then(r => {
			if (my_token !== _request_token) return;
			selected_customer = (r.message && r.message.customer) || null;
		});

		frappe.call({
			method: "cx_purisol.cx_purisol.api.consumption.list_available_coupons",
			args: { booklet },
			callback(r) {
				if (my_token !== _request_token) return;
				available_coupons = r.message || [];
				if (!available_coupons.length) {
					$checklist.html(`<div class="text-muted" style="padding:4px">${__("No available coupons in this booklet.")}</div>`);
					return;
				}
				available_coupons.forEach(function (c) {
					$checklist.append(`
						<label style="display:flex;align-items:center;padding:2px 4px">
							<input type="checkbox" class="coupon-tick" data-coupon="${c.coupon}" style="margin-right:6px">
							<span style="flex:1">${c.coupon} <span class="text-muted">(#${c.page_number})</span></span>
							<button type="button" class="btn btn-xs coupon-remove-btn" data-coupon="${c.coupon}" style="display:none;margin-left:8px;padding:2px 6px" title="${__("Remove from entry")}">
								<i class="fa fa-trash text-danger"></i>
							</button>
						</label>
					`);
				});
				_sync_checklist();
				$addBtn.prop("disabled", false);
			},
		});
	}

	// Booklet link field — use df.change so autocomplete selection is caught.
	let booklet_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			options: "Purisol Coupon Booklet",
			fieldname: "booklet_picker",
			label: __("Booklet"),
			placeholder: __("Select a booklet…"),
			change: _on_booklet_change,
			get_query: () => ({
				filters: { status: ["in", ["Sold", "In Custody", "In Stock"]] },
			}),
		},
		parent: $modeA.find(".booklet-link-wrapper"),
		render_input: true,
	});
	booklet_control.refresh();

	booklet_control.$input.on("awesomplete-selectcomplete change blur", _on_booklet_change);

	$checklist.on("click", ".coupon-remove-btn", function (e) {
		e.preventDefault();
		e.stopPropagation();
		const coupon = $(this).data("coupon");
		const row = (frm.doc.coupons || []).find(r => r.coupon === coupon);
		if (!row) return;
		frappe.model.clear_doc(row.doctype, row.name);
		frm.refresh_field("coupons");
		_sync_checklist();
	});

	$addBtn.on("click", function () {
		const ticked = $checklist.find(".coupon-tick:checked:not(:disabled)");
		if (!ticked.length) {
			frappe.msgprint(__("Please tick at least one coupon."));
			return;
		}
		const coupon_numbers = ticked.map(function () { return $(this).data("coupon"); }).get();

		frappe.call({
			method: "cx_purisol.cx_purisol.api.consumption.resolve_coupons",
			args: { coupon_numbers },
			callback(r) {
				const { resolved } = r.message || { resolved: [] };
				const consumable = resolved.filter(row => row.status !== "Consumed");
				const already_consumed = resolved.filter(row => row.status === "Consumed");

				_prune_empty_coupons();
				const existing = new Set((frm.doc.coupons || []).map(row => row.coupon));
				let added = 0;
				consumable.forEach(function (row) {
					if (existing.has(row.coupon)) return;
					frm.add_child("coupons", {
						coupon: row.coupon,
						booklet: selected_booklet,
						customer: selected_customer,
					});
					existing.add(row.coupon);
					added++;
				});
				if (added) frm.refresh_field("coupons");

				if (already_consumed.length) {
					already_consumed.forEach(function (row) {
						$checklist
							.find(`.coupon-tick[data-coupon="${row.coupon}"]`)
							.closest("label")
							.remove();
						available_coupons = available_coupons.filter(c => c.coupon !== row.coupon);
					});
					const names = already_consumed.map(r => r.coupon).join(", ");
					frappe.msgprint({
						title: __("Some coupons already consumed"),
						message: __(
							"The following coupons were consumed by another entry and were skipped: {0}",
							[names]
						),
						indicator: "orange",
					});
				}

				_sync_checklist();
			},
		});
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
