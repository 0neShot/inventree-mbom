/**
 * inventree-mbom: Manufacturing BOM & Routings Panel
 * Static JS module - handles panel interactivity, settings admin GUI,
 * inline timing edits, 1-click template application, and pricing page consolidation.
 */

// =========================================================
// Helper: CSRF Cookie
// =========================================================
function getCsrfToken() {
  const name = 'csrftoken';
  for (const cookie of document.cookie.split(';')) {
    const [k, v] = cookie.trim().split('=');
    if (k === name) return decodeURIComponent(v || '');
  }
  return '';
}

// Helper: API Request
async function mbomApi(path, opts = {}, pluginBase = '/plugin/inventree-mbom') {
  const url = path.startsWith('http') ? path : `${pluginBase}${path}`;
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
    ...(opts.headers || {}),
  };
  const token = localStorage.getItem('inventree-token') ||
                sessionStorage.getItem('inventree-token') ||
                localStorage.getItem('token') ||
                sessionStorage.getItem('token');
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Token ${token}`;
  }
  const res = await fetch(url, { ...opts, headers, credentials: 'include' });
  if (res.status === 204) return null;

  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }

  if (!res.ok) {
    const msg = data?.detail || data?.error || JSON.stringify(data) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

// Helper: Toast
function showMbomToast(message, type = 'success', duration = 3000) {
  const existing = document.getElementById('mbom-toast');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.id = 'mbom-toast';
  el.className = `mbom-toast mbom-toast--${type}`;
  const icon = type === 'error' ? 'exclamation-circle' : type === 'info' ? 'info-circle' : type === 'warning' ? 'exclamation-triangle' : 'check-circle';
  el.innerHTML = `<i class="fas fa-${icon}"></i> ${message}`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// =========================================================
// Main MbomPanel Class (Assembly Part Detail View)
// =========================================================
class MbomPanel {
  constructor(config) {
    this.partId       = config.partId;
    this.routingId    = config.routingId;
    this.pluginBase   = config.pluginBase || '/plugin/inventree-mbom';
    this.currency     = config.currency || 'EUR';
    this.batchSize    = config.batchSize || 1;

    // State
    this.ops          = [];
    this.laborRates   = config.laborRates   || [];
    this.machineCenters = config.machineCenters || [];
    this.templates    = config.templates    || [];

    // Drag state
    this._dragSrc     = null;
  }

  _csrf() { return getCsrfToken(); }
  api(path, opts = {}) { return mbomApi(path, opts, this.pluginBase); }
  toast(msg, type, dur) { showMbomToast(msg, type, dur); }

  // ---------------------------------------------------------
  // Cost Summary
  // ---------------------------------------------------------
  async loadCostSummary() {
    this._setCostLoading(true);
    try {
      const data = await this.api(`/cost-summary/${this.partId}/`);
      this._renderCostCards(data);
    } catch (e) {
      console.warn('[mBOM] cost summary error:', e.message);
    } finally {
      this._setCostLoading(false);
    }
  }

  _setCostLoading(isLoading) {
    ['mbom-c-material', 'mbom-c-labor', 'mbom-c-machine', 'mbom-c-total', 'mbom-c-co2'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('loading', isLoading);
    });
  }

  _renderCostCards(d) {
    const cur = this.currency;
    const fmt = (v, dec = 2) => parseFloat(v || 0).toFixed(dec);

    const matEl = document.getElementById('mbom-c-material');
    const labEl = document.getElementById('mbom-c-labor');
    const macEl = document.getElementById('mbom-c-machine');
    const totEl = document.getElementById('mbom-c-total');
    const co2El = document.getElementById('mbom-c-co2');

    if (matEl) {
      const min = fmt(d.material_cost, 2);
      const max = fmt(d.material_cost_max, 2);
      matEl.textContent = (min === max || parseFloat(max) <= 0) ? `${min} ${cur}` : `${min}..${max} ${cur}`;
    }
    if (labEl) labEl.textContent = `${fmt(d.labor_cost, 2)} ${cur}`;
    if (macEl) macEl.textContent = `${fmt(d.machine_cost, 2)} ${cur}`;
    if (totEl) {
      const tMin = fmt(d.per_unit_total_cost, 2);
      const tMax = fmt(d.per_unit_total_cost_max, 2);
      totEl.textContent = (tMin === tMax || parseFloat(tMax) <= 0) ? `${tMin} ${cur}` : `${tMin}..${tMax} ${cur}`;
    }
    if (co2El) co2El.textContent = `${fmt(d.co2_kg, 4)} kg`;

    const batchEl = document.getElementById('mbom-batch-display');
    if (batchEl) batchEl.textContent = d.batch_size;
    this.batchSize = d.batch_size;
  }

  // ---------------------------------------------------------
  // Operations: Load & Render
  // ---------------------------------------------------------
  async loadOperations() {
    if (!this.routingId) {
      try {
        const rList = await this.api(`/routing/?part=${this.partId}`);
        const routings = Array.isArray(rList) ? rList : (rList.results || []);
        if (routings.length > 0) {
          this.routingId = routings[0].pk;
          this.batchSize = routings[0].standard_batch_size || this.batchSize;
          const batchEl = document.getElementById('mbom-batch-input');
          if (batchEl) batchEl.value = this.batchSize;
        }
      } catch (e) {
        console.warn('[mBOM] routing lookup error:', e);
      }
    }

    if (!this.routingId) {
      this._renderEmpty();
      return;
    }

    const tbody = document.getElementById('mbom-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;">
      <span class="mbom-spinner"></span>&nbsp;Loading operations…
    </td></tr>`;

    try {
      const data = await this.api(`/operation/?routing=${this.routingId}`);
      this.ops = Array.isArray(data) ? data : (data.results || []);
      this._renderOpsTable(this.ops);
      this._populateParentSelect(this.ops);
    } catch (e) {
      const container = document.getElementById('mbom-ops-container');
      if (container) {
        container.innerHTML = `<div style="color:var(--bs-danger,#dc2626);padding:14px;background:var(--bs-danger-bg-subtle,#fee2e2);border-radius:6px;">
          <i class="fas fa-exclamation-triangle"></i> Error loading operations: ${e.message}
        </div>`;
      }
    }
  }

  _renderEmpty() {
    const container = document.getElementById('mbom-ops-container');
    if (!container) return;

    const templateOptions = (this.templates || []).map(t =>
      `<option value="${t.pk || t.id}">${t.name}</option>`
    ).join('');

    container.innerHTML = `
      <div class="mbom-empty mbom-quickstart-hero">
        <div class="mbom-quickstart-icon">⚙️</div>
        <h4 class="mbom-quickstart-title">Manufacturing Routing (mBOM)</h4>
        <p class="mbom-quickstart-sub">This assembly has no routing defined yet. Select a process template to generate operations instantly in 1 click, or start with a custom routing.</p>
        
        <div class="mbom-quickstart-actions">
          <div class="mbom-quickstart-template-bar">
            <select id="mbom-quick-template-select" class="mbom-select">
              <option value="">— Select Process Template… —</option>
              ${templateOptions}
            </select>
            <div style="display:flex;align-items:center;gap:6px;">
              <label for="mbom-quick-batch" style="font-size:0.8rem;opacity:0.75;">Batch:</label>
              <input type="number" id="mbom-quick-batch" value="${this.batchSize || 50}" min="1" style="width:60px;" class="mbom-input">
            </div>
            <button class="mbom-btn mbom-btn--primary" onclick="window._mbomPanel && window._mbomPanel.quickApplyTemplate()">
              <i class="fas fa-magic"></i>
              <span>Apply &amp; Generate Routing</span>
            </button>
          </div>

          <div class="mbom-quickstart-divider"><span>or</span></div>

          <button class="mbom-btn mbom-btn--ghost" onclick="window._mbomPanel && window._mbomPanel.createEmptyRouting()">
            <i class="fas fa-plus"></i>
            <span>+ Create Empty Routing</span>
          </button>
        </div>
      </div>`;
  }

  _renderOpsTable(ops) {
    const container = document.getElementById('mbom-ops-container');
    if (!container) return;

    if (!ops || ops.length === 0) {
      this._renderEmpty();
      return;
    }

    container.innerHTML = `
      <div class="mbom-table-wrapper">
        <table class="mbom-table" id="mbom-table">
          <thead>
            <tr>
              <th class="col-drag"></th>
              <th>Seq</th>
              <th>Operation</th>
              <th class="col-hide-sm">Labor Rate</th>
              <th class="col-hide-sm">Machine</th>
              <th style="text-align:right;">Setup (min)</th>
              <th style="text-align:right;">Cycle (min)</th>
              <th style="text-align:right;">Unit Cost</th>
              <th class="col-actions">Actions</th>
            </tr>
          </thead>
          <tbody id="mbom-tbody"></tbody>
        </table>
      </div>`;

    const tbody = document.getElementById('mbom-tbody');
    ops.forEach(op => {
      this._appendOpRow(tbody, op, false);
      (op.sub_operations || []).forEach(sub => {
        this._appendOpRow(tbody, sub, true, op.pk);
      });
    });

    this._initDragDrop();
  }

  _appendOpRow(tbody, op, isChild = false, parentId = null) {
    const row = document.createElement('tr');
    row.dataset.opId = op.pk;
    if (isChild) {
      row.dataset.parentId = parentId;
      row.className = 'mbom-row--child';
    } else {
      row.className = 'mbom-row--parent';
    }

    const subCount = (op.sub_operations || []).length;
    const toggleBtn = (!isChild && subCount > 0)
      ? `<button class="mbom-expand-btn expanded" data-parent="${op.pk}" title="Toggle sub-steps">
           <i class="fas fa-caret-right"></i>
         </button>`
      : '';

    const seqBadge = `<span class="mbom-seq-badge">${op.sequence_number}</span>`;
    const indent   = isChild ? '<span class="mbom-indent"></span>' : '';

    const laborChip = op.labor_rate
      ? `<span class="mbom-chip mbom-chip--labor" title="Labor">
           <i class="fas fa-user-hard-hat"></i>
           ${this._rateName(op.labor_rate, 'labor')}
         </span>`
      : '<span style="opacity:0.3">—</span>';

    const machineChip = op.machine_center
      ? `<span class="mbom-chip mbom-chip--machine" title="Machine">
           <i class="fas fa-cog"></i>
           ${this._rateName(op.machine_center, 'machine')}
         </span>`
      : '<span style="opacity:0.3">—</span>';

    const cost = parseFloat(op.per_unit_cost || 0).toFixed(4);

    row.innerHTML = `
      <td class="col-drag"><i class="fas fa-grip-vertical"></i></td>
      <td>${indent}${seqBadge}${toggleBtn}</td>
      <td>
        <strong>${op.name}</strong>
        ${op.description ? `<br><small style="opacity:0.6">${op.description}</small>` : ''}
      </td>
      <td class="col-hide-sm">${laborChip}</td>
      <td class="col-hide-sm">${machineChip}</td>
      <td style="text-align:right;">
        <input type="number" step="0.1" min="0" class="mbom-input" 
               value="${parseFloat(op.setup_time_minutes || 0).toFixed(2)}"
               onchange="window._mbomPanel && window._mbomPanel.inlineUpdateOp(${op.pk}, 'setup_time_minutes', this.value)"
               title="Click to edit setup time in minutes" 
               style="width:68px;padding:2px 4px;font-size:0.82rem;text-align:right;background:transparent;border:1px solid transparent;border-radius:4px;"
               onfocus="this.style.border='1px solid var(--bs-primary,#0d6efd)';this.style.background='var(--bs-body-bg,#fff)';"
               onblur="this.style.border='1px solid transparent';this.style.background='transparent';">
      </td>
      <td style="text-align:right;">
        <input type="number" step="0.1" min="0" class="mbom-input" 
               value="${parseFloat(op.run_time_per_unit_minutes || 0).toFixed(2)}"
               onchange="window._mbomPanel && window._mbomPanel.inlineUpdateOp(${op.pk}, 'run_time_per_unit_minutes', this.value)"
               title="Click to edit cycle time per unit in minutes" 
               style="width:68px;padding:2px 4px;font-size:0.82rem;text-align:right;background:transparent;border:1px solid transparent;border-radius:4px;"
               onfocus="this.style.border='1px solid var(--bs-primary,#0d6efd)';this.style.background='var(--bs-body-bg,#fff)';"
               onblur="this.style.border='1px solid transparent';this.style.background='transparent';">
      </td>
      <td class="mbom-cost-cell" style="text-align:right;">${cost} ${this.currency}</td>
      <td>
        <div class="mbom-actions">
          ${!isChild ? `<button class="mbom-btn mbom-btn--icon mbom-btn--info" onclick="window._mbomPanel.showAddSubOpModal(${op.pk})" title="Add sub-step">
            <i class="fas fa-level-down-alt"></i>
          </button>` : ''}
          <button class="mbom-btn mbom-btn--icon mbom-btn--warning" onclick="window._mbomPanel.showEditOpModal(${op.pk})" title="Edit">
            <i class="fas fa-edit"></i>
          </button>
          <button class="mbom-btn mbom-btn--icon mbom-btn--danger" onclick="window._mbomPanel.deleteOp(${op.pk})" title="Delete">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </td>`;

    tbody.appendChild(row);
  }

  _rateName(pk, type) {
    const list = type === 'labor' ? this.laborRates : this.machineCenters;
    const found = list.find(r => r.pk == pk || r.id == pk);
    return found ? found.name : `#${pk}`;
  }

  // ---------------------------------------------------------
  // Inline Editing & 1-Click Template Actions
  // ---------------------------------------------------------
  async inlineUpdateOp(opId, field, val) {
    try {
      await this.api(`/operation/${opId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: parseFloat(val) || 0 }),
      });
      await this.loadCostSummary();
      await this.loadOperations();
      this.toast('Updated operation timing');
    } catch (err) {
      this.toast(`Failed to update: ${err.message}`, 'error');
    }
  }

  async quickApplyTemplate() {
    const sel = document.getElementById('mbom-quick-template-select');
    const batchInput = document.getElementById('mbom-quick-batch');
    const tmplId = sel ? sel.value : '';
    const batchSize = batchInput ? parseInt(batchInput.value) || 50 : 50;

    if (!tmplId) {
      this.toast('Please select a process template to apply', 'warning');
      return;
    }

    try {
      const res = await this.api('/apply-template/', {
        method: 'POST',
        body: JSON.stringify({
          part_id: this.partId,
          template_id: parseInt(tmplId),
          batch_size: batchSize,
          overwrite: true,
        }),
      });

      this.routingId = res.pk || res.id || res.routing_id;
      this.batchSize = batchSize;
      this.toast('Process template applied & routing generated!');
      await this.loadCostSummary();
      await this.loadOperations();
    } catch (err) {
      this.toast(`Failed to apply template: ${err.message}`, 'error');
    }
  }

  async createEmptyRouting() {
    try {
      const res = await this.api('/routing/', {
        method: 'POST',
        body: JSON.stringify({
          part: this.partId,
          name: 'Default Routing',
          standard_batch_size: 50,
        }),
      });
      this.routingId = res.pk || res.id;
      this.toast('Empty routing created. Add operations below!');
      await this.loadCostSummary();
      await this.loadOperations();
    } catch (err) {
      this.toast(`Failed to create routing: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------
  // Drag-and-drop reordering
  // ---------------------------------------------------------
  _initDragDrop() {
    const tbody = document.getElementById('mbom-tbody');
    if (!tbody) return;

    tbody.addEventListener('dragstart', (e) => {
      const row = e.target.closest('tr[data-op-id]');
      if (!row) return;
      this._dragSrc = row;
      row.classList.add('mbom-row--dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', row.dataset.opId);
    });

    tbody.addEventListener('dragend', () => {
      document.querySelectorAll('.mbom-row--dragging, .mbom-row--drag-over').forEach(r => {
        r.classList.remove('mbom-row--dragging', 'mbom-row--drag-over');
      });
    });

    tbody.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const row = e.target.closest('tr[data-op-id]');
      if (row && row !== this._dragSrc) {
        document.querySelectorAll('.mbom-row--drag-over').forEach(r => r.classList.remove('mbom-row--drag-over'));
        row.classList.add('mbom-row--drag-over');
      }
    });

    tbody.addEventListener('drop', async (e) => {
      e.preventDefault();
      const target = e.target.closest('tr[data-op-id]');
      if (!target || target === this._dragSrc) return;

      const srcId = this._dragSrc.dataset.opId;
      const tgtId = target.dataset.opId;

      const srcOp = this._findOp(parseInt(srcId));
      const tgtOp = this._findOp(parseInt(tgtId));

      if (srcOp && tgtOp) {
        try {
          const [srcSeq, tgtSeq] = [srcOp.sequence_number, tgtOp.sequence_number];
          await this.api(`/operation/${srcId}/`, {
            method: 'PATCH',
            body: JSON.stringify({ sequence_number: tgtSeq }),
          });
          await this.api(`/operation/${tgtId}/`, {
            method: 'PATCH',
            body: JSON.stringify({ sequence_number: srcSeq }),
          });
          await this.loadOperations();
          this.toast('Operations reordered');
        } catch (err) {
          this.toast(`Reorder failed: ${err.message}`, 'error');
        }
      }
    });

    tbody.addEventListener('click', (e) => {
      const btn = e.target.closest('.mbom-expand-btn');
      if (!btn) return;
      const parentId = btn.dataset.parent;
      const childRows = document.querySelectorAll(`tr[data-parent-id="${parentId}"]`);
      const isExpanded = btn.classList.contains('expanded');
      childRows.forEach(r => r.style.display = isExpanded ? 'none' : '');
      btn.classList.toggle('expanded', !isExpanded);
    });
  }

  _findOp(pk) {
    for (const op of this.ops) {
      if (op.pk === pk) return op;
      for (const sub of (op.sub_operations || [])) {
        if (sub.pk === pk) return sub;
      }
    }
    return null;
  }

  _populateParentSelect(ops) {
    const sel = document.getElementById('mbom-f-parent');
    if (!sel) return;
    sel.innerHTML = '<option value="">— None (Top-level Operation) —</option>';
    ops.forEach(op => {
      const opt = document.createElement('option');
      opt.value = op.pk;
      opt.textContent = `${op.sequence_number}: ${op.name}`;
      sel.appendChild(opt);
    });
  }

  // ---------------------------------------------------------
  // Modals & Dialogs
  // ---------------------------------------------------------
  showAddOpModal(parentOpId = null) {
    this._resetOpForm();
    const title = document.getElementById('mbom-op-modal-title');
    if (title) title.textContent = parentOpId ? 'Add Sub-Operation' : 'Add Operation';

    const parentSel = document.getElementById('mbom-f-parent');
    if (parentSel && parentOpId) parentSel.value = parentOpId;

    const backdrop = document.getElementById('mbom-op-backdrop');
    if (backdrop) backdrop.classList.add('is-open');
  }

  showAddSubOpModal(parentOpId) {
    this.showAddOpModal(parentOpId);
  }

  showEditOpModal(pk) {
    const op = this._findOp(pk);
    if (!op) return;

    this._resetOpForm();
    const title = document.getElementById('mbom-op-modal-title');
    if (title) title.textContent = `Edit Operation: ${op.name}`;

    const idEl = document.getElementById('mbom-f-op-id');
    const seqEl = document.getElementById('mbom-f-seq');
    const nameEl = document.getElementById('mbom-f-name');
    const descEl = document.getElementById('mbom-f-desc');
    const parentSel = document.getElementById('mbom-f-parent');
    const laborSel = document.getElementById('mbom-f-labor');
    const machSel = document.getElementById('mbom-f-machine');
    const setupEl = document.getElementById('mbom-f-setup');
    const cycleEl = document.getElementById('mbom-f-cycle');

    if (idEl) idEl.value = op.pk;
    if (seqEl) seqEl.value = op.sequence_number;
    if (nameEl) nameEl.value = op.name;
    if (descEl) descEl.value = op.description || '';
    if (parentSel) parentSel.value = op.parent_operation || '';
    if (laborSel) laborSel.value = op.labor_rate || '';
    if (machSel) machSel.value = op.machine_center || '';
    if (setupEl) setupEl.value = op.setup_time_minutes;
    if (cycleEl) cycleEl.value = op.run_time_per_unit_minutes;

    const backdrop = document.getElementById('mbom-op-backdrop');
    if (backdrop) backdrop.classList.add('is-open');
  }

  showApplyTemplateDialog() {
    const backdrop = document.getElementById('mbom-tmpl-backdrop');
    if (backdrop) backdrop.classList.add('is-open');
  }

  _closeDialogs() {
    document.querySelectorAll('.mbom-backdrop').forEach(b => b.classList.remove('is-open'));
  }

  _resetOpForm() {
    const f = document.getElementById('mbom-op-form');
    if (f) f.reset();
    const idEl = document.getElementById('mbom-f-op-id');
    if (idEl) idEl.value = '';
  }

  async saveOp() {
    const idEl     = document.getElementById('mbom-f-op-id');
    const seqEl    = document.getElementById('mbom-f-seq');
    const nameEl   = document.getElementById('mbom-f-name');
    const descEl   = document.getElementById('mbom-f-desc');
    const parentEl = document.getElementById('mbom-f-parent');
    const laborEl  = document.getElementById('mbom-f-labor');
    const machEl   = document.getElementById('mbom-f-machine');
    const setupEl  = document.getElementById('mbom-f-setup');
    const cycleEl  = document.getElementById('mbom-f-cycle');

    if (!nameEl || !nameEl.value.trim()) {
      this.toast('Operation name is required', 'error');
      return;
    }
    if (!seqEl || !seqEl.value.trim()) {
      this.toast('Sequence number is required', 'error');
      return;
    }

    if (!this.routingId) {
      try {
        const res = await this.api('/routing/', {
          method: 'POST',
          body: JSON.stringify({
            part: this.partId,
            name: 'Default Routing',
            standard_batch_size: this.batchSize || 1,
          }),
        });
        this.routingId = res.pk || res.id;
      } catch (err) {
        this.toast(`Failed to create routing: ${err.message}`, 'error');
        return;
      }
    }

    const payload = {
      routing:                   this.routingId,
      sequence_number:           seqEl.value.trim(),
      name:                      nameEl.value.trim(),
      description:               descEl ? descEl.value.trim() : '',
      parent_operation:          (parentEl && parentEl.value) ? parseInt(parentEl.value) : null,
      labor_rate:                (laborEl && laborEl.value)   ? parseInt(laborEl.value)  : null,
      machine_center:            (machEl && machEl.value)     ? parseInt(machEl.value)   : null,
      setup_time_minutes:        parseFloat(setupEl?.value || 0) || 0,
      run_time_per_unit_minutes: parseFloat(cycleEl?.value || 0) || 0,
    };

    const opId = idEl ? idEl.value : null;
    const isEdit = !!opId;
    const path = isEdit ? `/operation/${opId}/` : '/operation/';
    const method = isEdit ? 'PUT' : 'POST';

    try {
      await this.api(path, { method, body: JSON.stringify(payload) });
      this._closeDialogs();
      this.toast(isEdit ? 'Operation updated' : 'Operation created');
      await this.loadCostSummary();
      await this.loadOperations();
    } catch (err) {
      this.toast(`Save failed: ${err.message}`, 'error');
    }
  }

  async deleteOp(pk) {
    if (!confirm('Are you sure you want to delete this operation? Any sub-operations will also be removed.')) return;
    try {
      await this.api(`/operation/${pk}/`, { method: 'DELETE' });
      this.toast('Operation deleted');
      await this.loadCostSummary();
      await this.loadOperations();
    } catch (err) {
      this.toast(`Delete failed: ${err.message}`, 'error');
    }
  }

  async applyTemplate() {
    const sel = document.getElementById('mbom-t-select');
    const batchInput = document.getElementById('mbom-t-batch');
    const overwriteBox = document.getElementById('mbom-t-overwrite');

    const tmplId = sel ? sel.value : null;
    if (!tmplId) {
      this.toast('Please select a template', 'error');
      return;
    }

    const payload = {
      part_id:     this.partId,
      template_id: parseInt(tmplId),
      batch_size:  batchInput ? (parseInt(batchInput.value) || 1) : 1,
      overwrite:   overwriteBox ? overwriteBox.checked : false,
    };

    try {
      const res = await this.api('/apply-template/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      this._closeDialogs();
      this.toast('Template applied successfully!');
      this.routingId = res.pk || res.id;
      await this.loadCostSummary();
      await this.loadOperations();
    } catch (err) {
      this.toast(`Apply failed: ${err.message}`, 'error');
    }
  }

  async updateBatchSize(newBatch) {
    const b = parseInt(newBatch);
    if (!b || b < 1) return;
    this.batchSize = b;

    if (this.routingId) {
      try {
        await this.api(`/routing/${this.routingId}/`, {
          method: 'PATCH',
          body: JSON.stringify({ standard_batch_size: b }),
        });
      } catch (e) {
        console.warn('[mBOM] batch size save error:', e);
      }
    }
    await this.loadCostSummary();
    await this.loadOperations();
  }

  // ---------------------------------------------------------
  // Init
  // ---------------------------------------------------------
  async init() {
    if (!this.templates.length || !this.laborRates.length || !this.machineCenters.length) {
      try {
        const [tmpls, labors, machines] = await Promise.all([
          this.api('/process-template/').catch(() => []),
          this.api('/labor-rate/').catch(() => []),
          this.api('/machine-center/').catch(() => []),
        ]);
        if (Array.isArray(tmpls)) this.templates = tmpls;
        if (Array.isArray(labors)) this.laborRates = labors;
        if (Array.isArray(machines)) this.machineCenters = machines;
      } catch (e) {
        console.warn('[mBOM] init tariff catalog error:', e);
      }
    }

    await this.loadCostSummary();
    await this.loadOperations();
  }
}

// =========================================================
// Settings Admin Panel: renderMbomSettingsPanel
// =========================================================
export async function renderMbomSettingsPanel(target, context) {
  if (!target) return;
  target.setAttribute('data-mbom-settings', 'true');

  target.innerHTML = `
    <div class="mbom-settings-container">
      <div class="mbom-settings-header">
        <div>
          <h3 style="margin:0 0 4px 0;font-size:1.15rem;font-weight:700;display:flex;align-items:center;gap:8px;">
            <span>⚙️</span>
            <span>Manufacturing (mBOM) Tariffs &amp; Templates</span>
          </h3>
          <p style="margin:0;font-size:0.84rem;opacity:0.65;">
            Central management for labor rates, machine centers, and reusable process routing templates.
          </p>
        </div>
        <button class="mbom-btn mbom-btn--ghost" id="mbom-settings-refresh-btn" title="Refresh data">
          <i class="fas fa-sync-alt"></i> <span>Refresh</span>
        </button>
      </div>

      <div class="mbom-settings-tabs">
        <button class="mbom-tab-btn active" data-tab="labor">
          <i class="fas fa-user-hard-hat"></i> Labor Rates (<span id="mbom-cnt-labor">…</span>)
        </button>
        <button class="mbom-tab-btn" data-tab="machine">
          <i class="fas fa-cog"></i> Machine Centers (<span id="mbom-cnt-machine">…</span>)
        </button>
        <button class="mbom-tab-btn" data-tab="templates">
          <i class="fas fa-magic"></i> Process Templates (<span id="mbom-cnt-tmpl">…</span>)
        </button>
      </div>

      <!-- Tab 1: Labor Rates -->
      <div class="mbom-settings-section active" id="mbom-sec-labor">
        <div class="mbom-settings-toolbar">
          <div style="font-size:0.85rem;opacity:0.75;">Labor tariff classes used to compute assembly cycle &amp; setup costs.</div>
          <button class="mbom-btn mbom-btn--success" id="mbom-add-labor-btn">
            <i class="fas fa-plus"></i> <span>Add Labor Rate</span>
          </button>
        </div>
        <div class="mbom-table-wrapper">
          <table class="mbom-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th style="text-align:right;">Hourly Rate</th>
                <th style="text-align:right;">Rate / Min</th>
                <th>Currency</th>
                <th>Status</th>
                <th class="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody id="mbom-tbody-labor">
              <tr><td colspan="8" style="text-align:center;padding:24px;"><span class="mbom-spinner"></span> Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 2: Machine Centers -->
      <div class="mbom-settings-section" id="mbom-sec-machine">
        <div class="mbom-settings-toolbar">
          <div style="font-size:0.85rem;opacity:0.75;">Machine centers, equipment rates, and CO₂ emission factors.</div>
          <button class="mbom-btn mbom-btn--success" id="mbom-add-machine-btn">
            <i class="fas fa-plus"></i> <span>Add Machine Center</span>
          </button>
        </div>
        <div class="mbom-table-wrapper">
          <table class="mbom-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th style="text-align:right;">Hourly Rate</th>
                <th style="text-align:right;">Rate / Min</th>
                <th style="text-align:right;">CO₂ (kg/min)</th>
                <th>Status</th>
                <th class="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody id="mbom-tbody-machine">
              <tr><td colspan="8" style="text-align:center;padding:24px;"><span class="mbom-spinner"></span> Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 3: Process Templates -->
      <div class="mbom-settings-section" id="mbom-sec-templates">
        <div class="mbom-settings-toolbar">
          <div style="font-size:0.85rem;opacity:0.75;">Reusable manufacturing process templates with parent &amp; child operations.</div>
          <button class="mbom-btn mbom-btn--primary" id="mbom-add-template-btn">
            <i class="fas fa-plus"></i> <span>New Process Template</span>
          </button>
        </div>
        <div id="mbom-tmpl-list-container">
          <div style="text-align:center;padding:24px;"><span class="mbom-spinner"></span> Loading templates…</div>
        </div>
      </div>

      <!-- Dynamic Settings Modal Container -->
      <div class="mbom-backdrop" id="mbom-settings-modal-backdrop">
        <div class="mbom-dialog" style="max-width:550px;">
          <div class="mbom-dialog__header">
            <h6 class="mbom-dialog__title" id="mbom-sm-title">Edit</h6>
            <button class="mbom-dialog__close" id="mbom-sm-close"><i class="fas fa-times"></i></button>
          </div>
          <div class="mbom-dialog__body" id="mbom-sm-body"></div>
          <div class="mbom-dialog__footer">
            <button class="mbom-btn mbom-btn--ghost" id="mbom-sm-cancel">Cancel</button>
            <button class="mbom-btn mbom-btn--primary" id="mbom-sm-save">Save Changes</button>
          </div>
        </div>
      </div>
    </div>
  `;

  // State cache
  let laborRates = [];
  let machineCenters = [];
  let templates = [];

  // Tab switching
  const tabs = target.querySelectorAll('.mbom-tab-btn');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      target.querySelectorAll('.mbom-settings-section').forEach(s => s.classList.remove('active'));
      btn.classList.add('active');
      const sec = target.querySelector(`#mbom-sec-${btn.dataset.tab}`);
      if (sec) sec.classList.add('active');
    });
  });

  // Modal helpers
  const modalBackdrop = target.querySelector('#mbom-settings-modal-backdrop');
  const modalTitle = target.querySelector('#mbom-sm-title');
  const modalBody = target.querySelector('#mbom-sm-body');
  const modalSave = target.querySelector('#mbom-sm-save');
  const modalClose = target.querySelector('#mbom-sm-close');
  const modalCancel = target.querySelector('#mbom-sm-cancel');

  let currentSaveHandler = null;

  function closeModal() {
    modalBackdrop.classList.remove('is-open');
    modalBody.innerHTML = '';
    currentSaveHandler = null;
  }
  modalClose.addEventListener('click', closeModal);
  modalCancel.addEventListener('click', closeModal);
  modalSave.addEventListener('click', () => {
    if (currentSaveHandler) currentSaveHandler();
  });

  // Load All
  async function loadAll() {
    try {
      const [lRes, mRes, tRes] = await Promise.all([
        mbomApi('/labor-rate/'),
        mbomApi('/machine-center/'),
        mbomApi('/process-template/'),
      ]);
      laborRates = Array.isArray(lRes) ? lRes : (lRes.results || []);
      machineCenters = Array.isArray(mRes) ? mRes : (mRes.results || []);
      templates = Array.isArray(tRes) ? tRes : (tRes.results || []);

      const cntL = target.querySelector('#mbom-cnt-labor');
      const cntM = target.querySelector('#mbom-cnt-machine');
      const cntT = target.querySelector('#mbom-cnt-tmpl');
      if (cntL) cntL.textContent = laborRates.length;
      if (cntM) cntM.textContent = machineCenters.length;
      if (cntT) cntT.textContent = templates.length;

      renderLaborTable();
      renderMachineTable();
      renderTemplatesList();
    } catch (err) {
      showMbomToast(`Failed to load tariffs: ${err.message}`, 'error');
    }
  }

  // 1. Labor Table
  function renderLaborTable() {
    const tbody = target.querySelector('#mbom-tbody-labor');
    if (!tbody) return;
    if (!laborRates.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;opacity:0.6;">No labor rates defined yet. Click "Add Labor Rate" to create one.</td></tr>';
      return;
    }
    tbody.innerHTML = laborRates.map(r => `
      <tr>
        <td><span class="mbom-seq-badge">${r.pk}</span></td>
        <td><strong>${r.name}</strong></td>
        <td><small style="opacity:0.7;">${r.description || '—'}</small></td>
        <td style="text-align:right;font-weight:600;">${parseFloat(r.hourly_rate).toFixed(2)}</td>
        <td style="text-align:right;opacity:0.8;">${parseFloat(r.rate_per_minute || (r.hourly_rate / 60)).toFixed(4)}</td>
        <td>${r.currency || 'EUR'}</td>
        <td>
          <span class="mbom-badge ${r.is_active ? 'mbom-badge--active' : 'mbom-badge--inactive'}">
            ${r.is_active ? 'Active' : 'Inactive'}
          </span>
        </td>
        <td>
          <div class="mbom-actions">
            <button class="mbom-btn mbom-btn--icon mbom-btn--warning" data-edit-labor="${r.pk}" title="Edit"><i class="fas fa-edit"></i></button>
            <button class="mbom-btn mbom-btn--icon mbom-btn--danger" data-del-labor="${r.pk}" title="Delete"><i class="fas fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `).join('');

    tbody.querySelectorAll('[data-edit-labor]').forEach(b => {
      b.addEventListener('click', () => openLaborModal(laborRates.find(r => r.pk == b.dataset.editLabor)));
    });
    tbody.querySelectorAll('[data-del-labor]').forEach(b => {
      b.addEventListener('click', () => deleteLaborRate(b.dataset.delLabor));
    });
  }

  function openLaborModal(r = null) {
    const isEdit = !!r;
    modalTitle.textContent = isEdit ? `Edit Labor Rate: ${r.name}` : 'New Labor Rate';
    modalBody.innerHTML = `
      <div class="mbom-form-group">
        <label class="mbom-form-label">Rate Name *</label>
        <input type="text" id="mbom-sm-l-name" class="mbom-input" value="${r ? r.name : ''}" placeholder="e.g. Senior Assembler">
      </div>
      <div class="mbom-form-group">
        <label class="mbom-form-label">Description</label>
        <input type="text" id="mbom-sm-l-desc" class="mbom-input" value="${r ? (r.description || '') : ''}">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="mbom-form-group">
          <label class="mbom-form-label">Hourly Rate *</label>
          <input type="number" step="0.01" id="mbom-sm-l-rate" class="mbom-input" value="${r ? r.hourly_rate : '45.00'}">
        </div>
        <div class="mbom-form-group">
          <label class="mbom-form-label">Currency</label>
          <input type="text" id="mbom-sm-l-cur" class="mbom-input" value="${r ? (r.currency || 'EUR') : 'EUR'}">
        </div>
      </div>
      <div class="mbom-form-group" style="margin-top:8px;">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85rem;">
          <input type="checkbox" id="mbom-sm-l-active" ${!r || r.is_active ? 'checked' : ''}>
          <span>Active Tariff</span>
        </label>
      </div>
    `;

    currentSaveHandler = async () => {
      const name = target.querySelector('#mbom-sm-l-name').value.trim();
      const rate = target.querySelector('#mbom-sm-l-rate').value;
      if (!name || !rate) return showMbomToast('Name and Hourly Rate are required', 'error');

      const payload = {
        name,
        description: target.querySelector('#mbom-sm-l-desc').value.trim(),
        hourly_rate: parseFloat(rate) || 0,
        currency: target.querySelector('#mbom-sm-l-cur').value.trim() || 'EUR',
        is_active: target.querySelector('#mbom-sm-l-active').checked,
      };

      try {
        if (isEdit) {
          await mbomApi(`/labor-rate/${r.pk}/`, { method: 'PUT', body: JSON.stringify(payload) });
          showMbomToast('Labor rate updated');
        } else {
          await mbomApi('/labor-rate/', { method: 'POST', body: JSON.stringify(payload) });
          showMbomToast('Labor rate created');
        }
        closeModal();
        await loadAll();
      } catch (e) {
        showMbomToast(`Save failed: ${e.message}`, 'error');
      }
    };

    modalBackdrop.classList.add('is-open');
  }

  async function deleteLaborRate(pk) {
    if (!confirm('Are you sure you want to delete this labor rate?')) return;
    try {
      await mbomApi(`/labor-rate/${pk}/`, { method: 'DELETE' });
      showMbomToast('Labor rate deleted');
      await loadAll();
    } catch (e) {
      showMbomToast(`Delete failed: ${e.message}`, 'error');
    }
  }

  // 2. Machine Table
  function renderMachineTable() {
    const tbody = target.querySelector('#mbom-tbody-machine');
    if (!tbody) return;
    if (!machineCenters.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;opacity:0.6;">No machine centers defined yet. Click "Add Machine Center" to create one.</td></tr>';
      return;
    }
    tbody.innerHTML = machineCenters.map(m => `
      <tr>
        <td><span class="mbom-seq-badge">${m.pk}</span></td>
        <td><strong>${m.name}</strong></td>
        <td><small style="opacity:0.7;">${m.description || '—'}</small></td>
        <td style="text-align:right;font-weight:600;">${parseFloat(m.hourly_rate).toFixed(2)} ${m.currency || 'EUR'}</td>
        <td style="text-align:right;opacity:0.8;">${parseFloat(m.rate_per_minute || (m.hourly_rate / 60)).toFixed(4)}</td>
        <td style="text-align:right;font-family:monospace;">${parseFloat(m.co2_factor_per_minute || 0).toFixed(6)}</td>
        <td>
          <span class="mbom-badge ${m.is_active ? 'mbom-badge--active' : 'mbom-badge--inactive'}">
            ${m.is_active ? 'Active' : 'Inactive'}
          </span>
        </td>
        <td>
          <div class="mbom-actions">
            <button class="mbom-btn mbom-btn--icon mbom-btn--warning" data-edit-mac="${m.pk}" title="Edit"><i class="fas fa-edit"></i></button>
            <button class="mbom-btn mbom-btn--icon mbom-btn--danger" data-del-mac="${m.pk}" title="Delete"><i class="fas fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `).join('');

    tbody.querySelectorAll('[data-edit-mac]').forEach(b => {
      b.addEventListener('click', () => openMachineModal(machineCenters.find(m => m.pk == b.dataset.editMac)));
    });
    tbody.querySelectorAll('[data-del-mac]').forEach(b => {
      b.addEventListener('click', () => deleteMachineCenter(b.dataset.delMac));
    });
  }

  function openMachineModal(m = null) {
    const isEdit = !!m;
    modalTitle.textContent = isEdit ? `Edit Machine Center: ${m.name}` : 'New Machine Center';
    modalBody.innerHTML = `
      <div class="mbom-form-group">
        <label class="mbom-form-label">Machine Name *</label>
        <input type="text" id="mbom-sm-m-name" class="mbom-input" value="${m ? m.name : ''}" placeholder="e.g. SMT Pick & Place">
      </div>
      <div class="mbom-form-group">
        <label class="mbom-form-label">Description</label>
        <input type="text" id="mbom-sm-m-desc" class="mbom-input" value="${m ? (m.description || '') : ''}">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="mbom-form-group">
          <label class="mbom-form-label">Hourly Rate *</label>
          <input type="number" step="0.01" id="mbom-sm-m-rate" class="mbom-input" value="${m ? m.hourly_rate : '60.00'}">
        </div>
        <div class="mbom-form-group">
          <label class="mbom-form-label">CO₂ Factor (kg/min)</label>
          <input type="number" step="0.0001" id="mbom-sm-m-co2" class="mbom-input" value="${m ? (m.co2_factor_per_minute || '0.0015') : '0.0015'}">
        </div>
      </div>
      <div class="mbom-form-group" style="margin-top:8px;">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85rem;">
          <input type="checkbox" id="mbom-sm-m-active" ${!m || m.is_active ? 'checked' : ''}>
          <span>Active Machine Center</span>
        </label>
      </div>
    `;

    currentSaveHandler = async () => {
      const name = target.querySelector('#mbom-sm-m-name').value.trim();
      const rate = target.querySelector('#mbom-sm-m-rate').value;
      if (!name || !rate) return showMbomToast('Name and Hourly Rate are required', 'error');

      const payload = {
        name,
        description: target.querySelector('#mbom-sm-m-desc').value.trim(),
        hourly_rate: parseFloat(rate) || 0,
        currency: 'EUR',
        co2_factor_per_minute: parseFloat(target.querySelector('#mbom-sm-m-co2').value || 0) || 0,
        is_active: target.querySelector('#mbom-sm-m-active').checked,
      };

      try {
        if (isEdit) {
          await mbomApi(`/machine-center/${m.pk}/`, { method: 'PUT', body: JSON.stringify(payload) });
          showMbomToast('Machine center updated');
        } else {
          await mbomApi('/machine-center/', { method: 'POST', body: JSON.stringify(payload) });
          showMbomToast('Machine center created');
        }
        closeModal();
        await loadAll();
      } catch (e) {
        showMbomToast(`Save failed: ${e.message}`, 'error');
      }
    };

    modalBackdrop.classList.add('is-open');
  }

  async function deleteMachineCenter(pk) {
    if (!confirm('Are you sure you want to delete this machine center?')) return;
    try {
      await mbomApi(`/machine-center/${pk}/`, { method: 'DELETE' });
      showMbomToast('Machine center deleted');
      await loadAll();
    } catch (e) {
      showMbomToast(`Delete failed: ${e.message}`, 'error');
    }
  }

  // 3. Process Templates List
  function renderTemplatesList() {
    const container = target.querySelector('#mbom-tmpl-list-container');
    if (!container) return;
    if (!templates.length) {
      container.innerHTML = '<div style="text-align:center;padding:24px;opacity:0.6;">No process templates defined. Click "New Process Template" to create one.</div>';
      return;
    }

    container.innerHTML = templates.map(t => {
      const steps = t.steps || [];
      return `
        <div class="mbom-tmpl-card">
          <div class="mbom-tmpl-header">
            <div>
              <div style="font-weight:700;font-size:0.95rem;display:flex;align-items:center;gap:8px;">
                <span>${t.name}</span>
                <span class="mbom-badge ${t.is_active ? 'mbom-badge--active' : 'mbom-badge--inactive'}">
                  ${t.is_active ? 'Active' : 'Inactive'}
                </span>
                <span style="font-size:0.75rem;opacity:0.65;font-weight:normal;">${steps.length} Root Steps</span>
              </div>
              ${t.description ? `<div style="font-size:0.8rem;opacity:0.7;margin-top:2px;">${t.description}</div>` : ''}
            </div>
            <div class="mbom-actions">
              <button class="mbom-btn mbom-btn--success" data-add-step="${t.pk}"><i class="fas fa-plus"></i> Add Step</button>
              <button class="mbom-btn mbom-btn--warning" data-edit-tmpl="${t.pk}"><i class="fas fa-edit"></i> Edit</button>
              <button class="mbom-btn mbom-btn--danger" data-del-tmpl="${t.pk}"><i class="fas fa-trash"></i> Delete</button>
            </div>
          </div>
          <div style="padding:10px 14px;">
            ${renderTemplateStepsTable(t, steps)}
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('[data-add-step]').forEach(b => {
      b.addEventListener('click', () => openStepModal(templates.find(t => t.pk == b.dataset.addStep), null));
    });
    container.querySelectorAll('[data-edit-tmpl]').forEach(b => {
      b.addEventListener('click', () => openTemplateModal(templates.find(t => t.pk == b.dataset.editTmpl)));
    });
    container.querySelectorAll('[data-del-tmpl]').forEach(b => {
      b.addEventListener('click', () => deleteTemplate(b.dataset.delTmpl));
    });

    container.querySelectorAll('[data-edit-step]').forEach(b => {
      const tmplId = b.dataset.tmplId;
      const stepId = b.dataset.editStep;
      const tmpl = templates.find(t => t.pk == tmplId);
      const step = findStepInTemplate(tmpl, stepId);
      b.addEventListener('click', () => openStepModal(tmpl, step));
    });
    container.querySelectorAll('[data-del-step]').forEach(b => {
      b.addEventListener('click', () => deleteStep(b.dataset.delStep));
    });
  }

  function findStepInTemplate(tmpl, stepId) {
    if (!tmpl || !tmpl.steps) return null;
    for (const s of tmpl.steps) {
      if (s.pk == stepId) return s;
      for (const sub of (s.sub_steps || [])) {
        if (sub.pk == stepId) return sub;
      }
    }
    return null;
  }

  function renderTemplateStepsTable(tmpl, steps) {
    if (!steps.length) {
      return '<div style="font-size:0.8rem;opacity:0.5;padding:8px 0;">No operations added to this template yet.</div>';
    }

    const rows = [];
    steps.forEach(s => {
      rows.push(renderStepRow(tmpl, s, false));
      (s.sub_steps || []).forEach(sub => {
        rows.push(renderStepRow(tmpl, sub, true));
      });
    });

    return `
      <table class="mbom-table" style="font-size:0.83rem;">
        <thead>
          <tr>
            <th style="width:70px;">Seq</th>
            <th>Operation / Step</th>
            <th>Labor Rate</th>
            <th>Machine</th>
            <th style="text-align:right;">Setup (min)</th>
            <th style="text-align:right;">Cycle (min)</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rows.join('')}
        </tbody>
      </table>
    `;
  }

  function renderStepRow(tmpl, s, isSub) {
    const lObj = laborRates.find(l => l.pk == s.labor_rate);
    const mObj = machineCenters.find(m => m.pk == s.machine_center);
    return `
      <tr style="${isSub ? 'opacity:0.85;' : ''}">
        <td>
          ${isSub ? `<span style="padding-left:14px;">↳</span> <span class="mbom-seq-badge" style="font-size:0.75rem;">${s.sequence_number}</span>` : `<span class="mbom-seq-badge">${s.sequence_number}</span>`}
        </td>
        <td>
          <strong>${s.name}</strong>
          ${s.description ? `<br><small style="opacity:0.6">${s.description}</small>` : ''}
        </td>
        <td>${lObj ? lObj.name : '—'}</td>
        <td>${mObj ? mObj.name : '—'}</td>
        <td style="text-align:right;">${parseFloat(s.setup_time_minutes || 0).toFixed(2)}</td>
        <td style="text-align:right;">${parseFloat(s.run_time_per_unit_minutes || 0).toFixed(2)}</td>
        <td>
          <div class="mbom-actions">
            <button class="mbom-btn mbom-btn--icon mbom-btn--warning" data-tmpl-id="${tmpl.pk}" data-edit-step="${s.pk}" title="Edit"><i class="fas fa-edit"></i></button>
            <button class="mbom-btn mbom-btn--icon mbom-btn--danger" data-del-step="${s.pk}" title="Delete"><i class="fas fa-trash"></i></button>
          </div>
        </td>
      </tr>
    `;
  }

  function openTemplateModal(t = null) {
    const isEdit = !!t;
    modalTitle.textContent = isEdit ? `Edit Template: ${t.name}` : 'New Process Template';
    modalBody.innerHTML = `
      <div class="mbom-form-group">
        <label class="mbom-form-label">Template Name *</label>
        <input type="text" id="mbom-sm-t-name" class="mbom-input" value="${t ? t.name : ''}" placeholder="e.g. SMT PCB Assembly Standard">
      </div>
      <div class="mbom-form-group">
        <label class="mbom-form-label">Description</label>
        <textarea id="mbom-sm-t-desc" class="mbom-input" rows="3">${t ? (t.description || '') : ''}</textarea>
      </div>
      <div class="mbom-form-group">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:0.85rem;">
          <input type="checkbox" id="mbom-sm-t-active" ${!t || t.is_active ? 'checked' : ''}>
          <span>Active Template</span>
        </label>
      </div>
    `;

    currentSaveHandler = async () => {
      const name = target.querySelector('#mbom-sm-t-name').value.trim();
      if (!name) return showMbomToast('Template name is required', 'error');

      const payload = {
        name,
        description: target.querySelector('#mbom-sm-t-desc').value.trim(),
        is_active: target.querySelector('#mbom-sm-t-active').checked,
      };

      try {
        if (isEdit) {
          await mbomApi(`/process-template/${t.pk}/`, { method: 'PUT', body: JSON.stringify(payload) });
          showMbomToast('Template updated');
        } else {
          await mbomApi('/process-template/', { method: 'POST', body: JSON.stringify(payload) });
          showMbomToast('Template created');
        }
        closeModal();
        await loadAll();
      } catch (e) {
        showMbomToast(`Save failed: ${e.message}`, 'error');
      }
    };

    modalBackdrop.classList.add('is-open');
  }

  async function deleteTemplate(pk) {
    if (!confirm('Are you sure you want to delete this process template and all its steps?')) return;
    try {
      await mbomApi(`/process-template/${pk}/`, { method: 'DELETE' });
      showMbomToast('Template deleted');
      await loadAll();
    } catch (e) {
      showMbomToast(`Delete failed: ${e.message}`, 'error');
    }
  }

  function openStepModal(tmpl, step = null) {
    const isEdit = !!step;
    modalTitle.textContent = isEdit ? `Edit Step: ${step.name}` : `Add Step to ${tmpl.name}`;

    const parentOptions = (tmpl.steps || [])
      .filter(s => !isEdit || s.pk != step.pk)
      .map(s => `<option value="${s.pk}" ${step && step.parent_step == s.pk ? 'selected' : ''}>${s.sequence_number}: ${s.name}</option>`)
      .join('');

    const laborOptions = laborRates.map(l =>
      `<option value="${l.pk}" ${step && step.labor_rate == l.pk ? 'selected' : ''}>${l.name} (${parseFloat(l.hourly_rate).toFixed(2)} EUR/h)</option>`
    ).join('');

    const machineOptions = machineCenters.map(m =>
      `<option value="${m.pk}" ${step && step.machine_center == m.pk ? 'selected' : ''}>${m.name} (${parseFloat(m.hourly_rate).toFixed(2)} EUR/h)</option>`
    ).join('');

    modalBody.innerHTML = `
      <div style="display:grid;grid-template-columns:100px 1fr;gap:10px;">
        <div class="mbom-form-group">
          <label class="mbom-form-label">Sequence *</label>
          <input type="text" id="mbom-sm-s-seq" class="mbom-input" value="${step ? step.sequence_number : '10'}">
        </div>
        <div class="mbom-form-group">
          <label class="mbom-form-label">Step Name *</label>
          <input type="text" id="mbom-sm-s-name" class="mbom-input" value="${step ? step.name : ''}" placeholder="e.g. SMT Placement">
        </div>
      </div>
      <div class="mbom-form-group">
        <label class="mbom-form-label">Parent Step (Optional for sub-steps)</label>
        <select id="mbom-sm-s-parent" class="mbom-select">
          <option value="">— None (Root Operation) —</option>
          ${parentOptions}
        </select>
      </div>
      <div class="mbom-form-group">
        <label class="mbom-form-label">Description</label>
        <input type="text" id="mbom-sm-s-desc" class="mbom-input" value="${step ? (step.description || '') : ''}">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="mbom-form-group">
          <label class="mbom-form-label">Labor Rate</label>
          <select id="mbom-sm-s-labor" class="mbom-select">
            <option value="">— None —</option>
            ${laborOptions}
          </select>
        </div>
        <div class="mbom-form-group">
          <label class="mbom-form-label">Machine Center</label>
          <select id="mbom-sm-s-machine" class="mbom-select">
            <option value="">— None —</option>
            ${machineOptions}
          </select>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="mbom-form-group">
          <label class="mbom-form-label">Setup Time (minutes)</label>
          <input type="number" step="0.1" min="0" id="mbom-sm-s-setup" class="mbom-input" value="${step ? step.setup_time_minutes : '0.0'}">
        </div>
        <div class="mbom-form-group">
          <label class="mbom-form-label">Cycle / Run Time (minutes/unit)</label>
          <input type="number" step="0.1" min="0" id="mbom-sm-s-cycle" class="mbom-input" value="${step ? step.run_time_per_unit_minutes : '1.0'}">
        </div>
      </div>
    `;

    currentSaveHandler = async () => {
      const seq = target.querySelector('#mbom-sm-s-seq').value.trim();
      const name = target.querySelector('#mbom-sm-s-name').value.trim();
      if (!seq || !name) return showMbomToast('Sequence and Name are required', 'error');

      const parentVal = target.querySelector('#mbom-sm-s-parent').value;
      const laborVal = target.querySelector('#mbom-sm-s-labor').value;
      const machVal = target.querySelector('#mbom-sm-s-machine').value;

      const payload = {
        template: tmpl.pk,
        sequence_number: seq,
        name,
        description: target.querySelector('#mbom-sm-s-desc').value.trim(),
        parent_step: parentVal ? parseInt(parentVal) : null,
        labor_rate: laborVal ? parseInt(laborVal) : null,
        machine_center: machVal ? parseInt(machVal) : null,
        setup_time_minutes: parseFloat(target.querySelector('#mbom-sm-s-setup').value || 0) || 0,
        run_time_per_unit_minutes: parseFloat(target.querySelector('#mbom-sm-s-cycle').value || 0) || 0,
      };

      try {
        if (isEdit) {
          await mbomApi(`/process-template-step/${step.pk}/`, { method: 'PUT', body: JSON.stringify(payload) });
          showMbomToast('Template step updated');
        } else {
          await mbomApi('/process-template-step/', { method: 'POST', body: JSON.stringify(payload) });
          showMbomToast('Template step added');
        }
        closeModal();
        await loadAll();
      } catch (e) {
        showMbomToast(`Save failed: ${e.message}`, 'error');
      }
    };

    modalBackdrop.classList.add('is-open');
  }

  async function deleteStep(pk) {
    if (!confirm('Are you sure you want to delete this template step?')) return;
    try {
      await mbomApi(`/process-template-step/${pk}/`, { method: 'DELETE' });
      showMbomToast('Template step deleted');
      await loadAll();
    } catch (e) {
      showMbomToast(`Delete failed: ${e.message}`, 'error');
    }
  }

  // Buttons listeners
  target.querySelector('#mbom-settings-refresh-btn').addEventListener('click', loadAll);
  target.querySelector('#mbom-add-labor-btn').addEventListener('click', () => openLaborModal(null));
  target.querySelector('#mbom-add-machine-btn').addEventListener('click', () => openMachineModal(null));
  target.querySelector('#mbom-add-template-btn').addEventListener('click', () => openTemplateModal(null));

  // Initial load
  await loadAll();
  initPricingObserver();
}

// =========================================================
// Native Pricing Page Accordion Observer (/web/part/<id>/pricing)
// =========================================================
let pricingObserverInitialized = false;

export function initPricingObserver() {
  if (pricingObserverInitialized) return;
  pricingObserverInitialized = true;

  // Intercept history for SPA navigation
  const origPush = history.pushState;
  history.pushState = function() {
    origPush.apply(this, arguments);
    checkAndInjectPricing();
  };
  const origReplace = history.replaceState;
  history.replaceState = function() {
    origReplace.apply(this, arguments);
    checkAndInjectPricing();
  };
  window.addEventListener('popstate', checkAndInjectPricing);

  // MutationObserver for SPA DOM updates
  const observer = new MutationObserver(() => {
    checkAndInjectPricing();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // Initial check
  checkAndInjectPricing();
}

let isInjectingPricing = false;

async function checkAndInjectPricing() {
  const match = window.location.pathname.match(/\/web\/part\/(\d+)\/pricing/);
  if (!match) return;

  const partId = match[1];
  if (document.getElementById('mbom-pricing-accordion')) return;
  if (isInjectingPricing) return;
  isInjectingPricing = true;

  try {
    const data = await mbomApi(`/cost-summary/${partId}/`);
    if (!data || !data.has_routing) return;

    if (document.getElementById('mbom-pricing-accordion')) return;

    // Find the pricing container or card
    const container = findPricingMountTarget();
    if (!container) return;

    const cur = data.currency || 'EUR';
    const accordion = document.createElement('div');
    accordion.id = 'mbom-pricing-accordion';
    accordion.className = 'mbom-pricing-accordion mantine-Paper-root';
    accordion.style.cssText = 'margin:16px 0;border:1px solid var(--bs-border-color,#dee2e6);border-radius:8px;overflow:hidden;background:var(--bs-body-bg,#fff);';

    accordion.innerHTML = `
      <div class="mbom-accordion-header" id="mbom-acc-toggle" style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--bs-secondary-bg,#f8f9fa);cursor:pointer;user-select:none;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:1.1rem;">⚙️</span>
          <span style="font-weight:700;font-size:0.95rem;">mBOM Pricing (Manufacturing Operations)</span>
          <span class="mbom-badge mbom-badge--active" style="background:rgba(25,135,84,0.15);color:#198754;font-weight:600;padding:2px 8px;border-radius:12px;font-size:0.75rem;">
            +${parseFloat(data.per_unit_manufacturing_cost || 0).toFixed(4)} ${cur} / unit
          </span>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:0.8rem;opacity:0.7;">Batch: ${data.batch_size}</span>
          <span class="mbom-accordion-chevron" style="font-size:0.8rem;transition:transform 0.2s ease;">▼</span>
        </div>
      </div>
      <div class="mbom-accordion-body" style="padding:16px;">
        <div class="mbom-kpi-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px;">
          <div class="mbom-kpi">
            <div class="mbom-kpi__label">Labor Cost</div>
            <div class="mbom-kpi__val">${parseFloat(data.labor_cost || 0).toFixed(2)} ${cur}</div>
            <div class="mbom-kpi__sub">Setup: ${parseFloat(data.labor_setup_cost || 0).toFixed(2)} | Run: ${parseFloat(data.labor_run_cost || 0).toFixed(2)}</div>
          </div>
          <div class="mbom-kpi">
            <div class="mbom-kpi__label">Machine Cost</div>
            <div class="mbom-kpi__val">${parseFloat(data.machine_cost || 0).toFixed(2)} ${cur}</div>
            <div class="mbom-kpi__sub">Setup: ${parseFloat(data.machine_setup_cost || 0).toFixed(2)} | Run: ${parseFloat(data.machine_run_cost || 0).toFixed(2)}</div>
          </div>
          <div class="mbom-kpi">
            <div class="mbom-kpi__label">Setup vs Run</div>
            <div class="mbom-kpi__val">${parseFloat(data.setup_total || 0).toFixed(2)} / ${parseFloat(data.run_total || 0).toFixed(2)}</div>
            <div class="mbom-kpi__sub">Setup split vs Run batch</div>
          </div>
          <div class="mbom-kpi">
            <div class="mbom-kpi__label">CO₂ Equivalent</div>
            <div class="mbom-kpi__val">${parseFloat(data.co2_kg || 0).toFixed(4)} kg</div>
            <div class="mbom-kpi__sub">Batch footprint</div>
          </div>
          <div class="mbom-kpi">
            <div class="mbom-kpi__label">Per-Unit Mfg</div>
            <div class="mbom-kpi__val" style="color:#198754;">+${parseFloat(data.per_unit_manufacturing_cost || 0).toFixed(4)} ${cur}</div>
            <div class="mbom-kpi__sub">Added to Overall Pricing</div>
          </div>
        </div>

        ${data.operations && data.operations.length > 0 ? `
          <div style="margin-top:12px;">
            <div style="font-size:0.82rem;font-weight:600;margin-bottom:6px;opacity:0.8;">Operations Breakdown</div>
            <div style="overflow-x:auto;">
              <table class="mbom-table" style="width:100%;font-size:0.82rem;">
                <thead>
                  <tr>
                    <th>Seq</th>
                    <th>Operation</th>
                    <th>Labor Class</th>
                    <th>Machine Center</th>
                    <th style="text-align:right;">Setup (min)</th>
                    <th style="text-align:right;">Cycle (min)</th>
                    <th style="text-align:right;">Unit Cost</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.operations.map(op => `
                    <tr>
                      <td><span class="mbom-seq-badge">${op.sequence_number}</span></td>
                      <td><strong>${op.name}</strong></td>
                      <td>${op.labor_rate_name}</td>
                      <td>${op.machine_name}</td>
                      <td style="text-align:right;">${parseFloat(op.setup_min || 0).toFixed(2)}</td>
                      <td style="text-align:right;">${parseFloat(op.cycle_min || 0).toFixed(2)}</td>
                      <td style="text-align:right;font-weight:600;">${parseFloat(op.per_unit_cost || 0).toFixed(4)} ${cur}</td>
                    </tr>
                    ${(op.sub_operations || []).map(sub => `
                      <tr style="opacity:0.85;">
                        <td style="padding-left:20px;">↳ <span class="mbom-seq-badge" style="font-size:0.75rem;">${sub.sequence_number}</span></td>
                        <td>${sub.name}</td>
                        <td>${sub.labor_rate_name}</td>
                        <td>${sub.machine_name}</td>
                        <td style="text-align:right;">${parseFloat(sub.setup_min || 0).toFixed(2)}</td>
                        <td style="text-align:right;">${parseFloat(sub.cycle_min || 0).toFixed(2)}</td>
                        <td style="text-align:right;">${parseFloat(sub.per_unit_cost || 0).toFixed(4)} ${cur}</td>
                      </tr>
                    `).join('')}
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}

        <div class="mbom-rollup-note" style="margin-top:12px;font-size:0.78rem;opacity:0.75;display:flex;align-items:center;gap:6px;">
          <span>ℹ️</span>
          <span>mBOM manufacturing cost is rolled into the <strong>Overall Pricing</strong> card above: Overall Cost = Material (eBOM) + Manufacturing (mBOM).</span>
        </div>
      </div>
    `;

    const toggle = accordion.querySelector('#mbom-acc-toggle');
    const chevron = accordion.querySelector('.mbom-accordion-chevron');
    const body = accordion.querySelector('.mbom-accordion-body');
    let open = true;
    toggle.addEventListener('click', () => {
      open = !open;
      body.style.display = open ? 'block' : 'none';
      chevron.style.transform = open ? 'rotate(0deg)' : 'rotate(-90deg)';
    });

    // Insert into container
    container.parentNode.insertBefore(accordion, container.nextSibling || container);
  } catch (err) {
    console.warn('[mBOM] pricing injection notice:', err.message);
  } finally {
    isInjectingPricing = false;
  }
}

function findPricingMountTarget() {
  // Look for BOM Pricing card or Overall Pricing card in the pricing panel
  const allCards = Array.from(document.querySelectorAll('.mantine-Paper-root, [role="tabpanel"] > div, .mantine-Tabs-panel > div'));
  for (const card of allCards) {
    const text = card.textContent || '';
    if (text.includes('BOM Pricing') || text.includes('Overall Pricing')) {
      return card;
    }
  }
  const tabpanel = document.querySelector('[role="tabpanel"], .mantine-Tabs-panel');
  if (tabpanel) return tabpanel.firstElementChild || tabpanel;
  return null;
}

// =========================================================
// Main Export: renderMbomPanel (Assembly Part Detail Tab)
// =========================================================
export async function renderMbomPanel(target, context) {
  if (!target) return;

  let partId = context?.target_id || context?.id || context?.instance?.pk || context?.instance?.id;
  if (!partId) {
    const match = window.location.pathname.match(/\/part\/(\d+)/);
    if (match) partId = match[1];
  }
  if (!partId) {
    target.innerHTML = '<div style="padding:16px;color:#dc2626;">Error: Could not identify Part ID.</div>';
    return;
  }

  // Ensure CSS is loaded
  if (!document.getElementById('inventree-mbom-css')) {
    const link = document.createElement('link');
    link.id = 'inventree-mbom-css';
    link.rel = 'stylesheet';
    link.href = '/static/plugins/inventree-mbom/inventree_mbom/css/mbom.css';
    document.head.appendChild(link);
  }

  target.setAttribute('data-mbom-panel', 'true');
  target.innerHTML = '<div style="padding:24px;text-align:center;color:#6b7280;"><span class="mbom-spinner"></span> Loading Manufacturing BOM &amp; Routings…</div>';

  try {
    const headers = { 'Accept': 'text/html, */*' };
    const token = localStorage.getItem('inventree-token') ||
                  sessionStorage.getItem('inventree-token') ||
                  localStorage.getItem('token') ||
                  sessionStorage.getItem('token');
    if (token) headers['Authorization'] = `Token ${token}`;

    const res = await fetch(`/plugin/inventree-mbom/panel/part/${partId}/`, {
      headers,
      credentials: 'include',
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const html = await res.text();

    const temp = document.createElement('div');
    temp.innerHTML = html;
    target.innerHTML = '';
    while (temp.firstChild) {
      target.appendChild(temp.firstChild);
    }

    // Config extraction
    let config = null;
    const scripts = target.querySelectorAll('script');
    scripts.forEach(s => {
      try {
        (new Function(s.textContent))();
        if (window.MBOM_CONFIG) config = window.MBOM_CONFIG;
      } catch (e) {
        console.warn('[mBOM] Script evaluation notice:', e);
      }
    });

    if (!config) {
      config = {
        partId: parseInt(partId),
        routingId: null,
        pluginBase: '/plugin/inventree-mbom',
        currency: 'EUR',
        batchSize: 50,
        laborRates: [],
        machineCenters: [],
        templates: [],
      };
    }

    window.MBOM_CONFIG = config;
    const panel = new MbomPanel(config);
    window._mbomPanel = panel;
    window.MBOM_PANEL = panel;
    await panel.init();

    // Start pricing observer
    initPricingObserver();
  } catch (err) {
    target.innerHTML = `<div style="padding:16px;color:#dc2626;background:#fee2e2;border-radius:8px;">
      <strong>Error loading mBOM panel:</strong> ${err.message}
    </div>`;
  }
}

// Fallback export for pricing panel if queried directly
export async function renderMbomPricingPanel(target, context) {
  if (!target) return;
  let partId = context?.target_id || context?.id || context?.instance?.pk || context?.instance?.id;
  if (!partId) {
    const m = window.location.pathname.match(/\/part\/(\d+)/);
    if (m) partId = m[1];
  }
  target.innerHTML = '<div style="padding:12px;color:#6b7280;">Loading pricing…</div>';
  try {
    const headers = { 'Accept': 'text/html, */*' };
    const res = await fetch(`/plugin/inventree-mbom/pricing-panel/${partId}/`, { headers, credentials: 'include' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    target.innerHTML = await res.text();
  } catch (err) {
    target.innerHTML = `<div style="padding:12px;color:#dc2626;">Error: ${err.message}</div>`;
  }
}

// Automatically start pricing observer
initPricingObserver();