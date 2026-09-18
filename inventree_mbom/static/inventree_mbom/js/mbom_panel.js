/**
 * inventree-mbom: Manufacturing BOM & Routings Panel
 * Static JS module - handles all panel interactivity
 *
 * Architecture:
 *   MbomPanel class encapsulates all state and DOM manipulation.
 *   Instantiated once per panel mount with PART_ID and ROUTING_ID.
 *   Uses fetch() with CSRF cookies for API calls.
 */

class MbomPanel {
  constructor(config) {
    this.partId       = config.partId;
    this.routingId    = config.routingId;        // null if no routing yet
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
    this._dragSrcSeq  = null;
  }

  // =========================================================
  // CSRF helper
  // =========================================================
  _csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  // =========================================================
  // API wrapper
  // =========================================================
  async api(path, opts = {}) {
    const url = path.startsWith('http') ? path : `${this.pluginBase}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      'X-CSRFToken': this._csrf(),
      ...(opts.headers || {}),
    };
    const res = await fetch(url, { ...opts, headers, credentials: 'same-origin' });

    if (res.status === 204) return null;  // No content (DELETE)

    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { detail: text }; }

    if (!res.ok) {
      const msg = data?.detail || data?.error || JSON.stringify(data) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  // =========================================================
  // Toast notifications
  // =========================================================
  toast(message, type = 'success', duration = 3000) {
    const existing = document.getElementById('mbom-toast');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.id = 'mbom-toast';
    el.className = `mbom-toast mbom-toast--${type}`;
    el.innerHTML = `<i class="fas fa-${type === 'error' ? 'exclamation-circle' : type === 'info' ? 'info-circle' : 'check-circle'}"></i> ${message}`;
    document.body.appendChild(el);

    setTimeout(() => el.remove(), duration);
  }

  // =========================================================
  // Cost Summary
  // =========================================================
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

  _setCostLoading(on) {
    ['mbom-c-material', 'mbom-c-labor', 'mbom-c-machine', 'mbom-c-total', 'mbom-c-co2'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        if (on) el.classList.add('loading');
        else el.classList.remove('loading');
      }
    });
  }

  _renderCostCards(d) {
    const fmt = (v) => `${parseFloat(v || 0).toFixed(4)} ${this.currency}`;
    const fmtCo2 = (v) => `${parseFloat(v || 0).toFixed(4)} kg`;

    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el) { el.textContent = val; el.classList.remove('loading'); }
    };

    set('mbom-c-material', fmt(d.material_cost));
    set('mbom-c-labor',    fmt(d.labor_cost));
    set('mbom-c-machine',  fmt(d.machine_cost));
    set('mbom-c-total',    fmt(d.per_unit_total_cost));
    set('mbom-c-co2',      fmtCo2(d.co2_kg));

    // Update batch info display
    const batchEl = document.getElementById('mbom-batch-display');
    if (batchEl) batchEl.textContent = d.batch_size;
    this.batchSize = d.batch_size;
  }

  // =========================================================
  // Operations: Load & Render
  // =========================================================
  async loadOperations() {
    if (!this.routingId) {
      this._renderEmpty();
      return;
    }

    const tbody = document.getElementById('mbom-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:20px;">
      <span class="mbom-spinner"></span>&nbsp;Loading operationsâ€¦
    </td></tr>`;

    try {
      // Fetch all ops for this routing (top-level filter, sub-ops nested in serializer)
      const data = await this.api(`/operation/?routing=${this.routingId}`);
      this.ops = Array.isArray(data) ? data : (data.results || []);
      this._renderOpsTable(this.ops);
      this._populateParentSelect(this.ops);
    } catch (e) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="color:var(--bs-danger,red);padding:14px;">
        <i class="fas fa-exclamation-triangle"></i> ${e.message}
      </td></tr>`;
    }
  }

  _renderEmpty() {
    const container = document.getElementById('mbom-ops-container');
    if (!container) return;
    container.innerHTML = `
      <div class="mbom-empty">
        <i class="fas fa-route mbom-empty__icon"></i>
        <div class="mbom-empty__title">No routing defined</div>
        <div class="mbom-empty__sub">Apply a process template or add an operation to begin.</div>
      </div>`;
  }

  _renderOpsTable(ops) {
    const container = document.getElementById('mbom-ops-container');
    if (!container) return;

    if (!ops || ops.length === 0) {
      container.innerHTML = `
        <div class="mbom-empty">
          <i class="fas fa-list mbom-empty__icon"></i>
          <div class="mbom-empty__title">No operations yet</div>
          <div class="mbom-empty__sub">Click <strong>Add Operation</strong> or apply a template.</div>
        </div>`;
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
              <th>Setup (min)</th>
              <th>Cycle (min)</th>
              <th>Unit Cost</th>
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

  _appendOpRow(tbody, op, isChild, parentPk) {
    const row = document.createElement('tr');
    row.dataset.opId     = op.pk;
    row.dataset.isChild  = isChild ? '1' : '0';
    row.dataset.parentId = parentPk || '';
    row.className = isChild ? 'mbom-row--child' : 'mbom-row--parent';
    row.draggable = true;

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
      : '<span style="opacity:0.3">â€”</span>';

    const machineChip = op.machine_center
      ? `<span class="mbom-chip mbom-chip--machine" title="Machine">
           <i class="fas fa-cog"></i>
           ${this._rateName(op.machine_center, 'machine')}
         </span>`
      : '<span style="opacity:0.3">â€”</span>';

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
      <td>${parseFloat(op.setup_time_minutes || 0).toFixed(2)}</td>
      <td>${parseFloat(op.run_time_per_unit_minutes || 0).toFixed(2)}</td>
      <td class="mbom-cost-cell">${cost} ${this.currency}</td>
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

  // =========================================================
  // Drag-and-drop reordering
  // =========================================================
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

    tbody.addEventListener('dragend', (e) => {
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

      const srcId  = this._dragSrc.dataset.opId;
      const tgtId  = target.dataset.opId;

      // Get new sequence by adopting target's seq +0.5 (visual feedback only for now)
      // Then reload to get server-canonical order
      // Actual reorder: PATCH sequence_number to swap them
      const srcOp = this._findOp(parseInt(srcId));
      const tgtOp = this._findOp(parseInt(tgtId));

      if (srcOp && tgtOp) {
        // Swap sequence numbers
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

    // Toggle expand/collapse sub-rows
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

  // =========================================================
  // Parent select population
  // =========================================================
  _populateParentSelect(ops) {
    const sel = document.getElementById('mbom-op-parent');
    if (!sel) return;
    while (sel.options.length > 1) sel.remove(1);
    ops.forEach(op => {
      const opt = document.createElement('option');
      opt.value = op.pk;
      opt.textContent = `[${op.sequence_number}] ${op.name}`;
      sel.appendChild(opt);
    });
  }

  // =========================================================
  // Dialog management
  // =========================================================
  _openDialog(id) {
    document.getElementById(id)?.classList.add('open');
  }

  _closeDialogs() {
    document.querySelectorAll('.mbom-backdrop.open').forEach(d => d.classList.remove('open'));
  }

  // =========================================================
  // Apply Template Dialog
  // =========================================================
  showApplyTemplateDialog() {
    document.getElementById('mbom-tmpl-select').value = '';
    document.getElementById('mbom-tmpl-batch').value  = this.batchSize;
    document.getElementById('mbom-tmpl-overwrite').value = 'false';
    this._openDialog('mbom-tmpl-backdrop');
  }

  async applyTemplate() {
    const templateId = document.getElementById('mbom-tmpl-select').value;
    if (!templateId) { this.toast('Please select a template', 'error'); return; }

    const btn = document.getElementById('mbom-tmpl-apply-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="mbom-spinner"></span> Applyingâ€¦';

    try {
      await this.api('/apply-template/', {
        method: 'POST',
        body: JSON.stringify({
          part_id:     this.partId,
          template_id: parseInt(templateId),
          overwrite:   document.getElementById('mbom-tmpl-overwrite').value === 'true',
          batch_size:  parseInt(document.getElementById('mbom-tmpl-batch').value) || 1,
        }),
      });
      this._closeDialogs();
      this.toast('Template applied successfully!');
      // Reload page to pick up new routing ID if it was just created
      setTimeout(() => location.reload(), 800);
    } catch (e) {
      this.toast(e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-magic"></i> Apply';
    }
  }

  // =========================================================
  // Add / Edit Operation Dialog
  // =========================================================
  _resetOpForm() {
    ['mbom-op-id', 'mbom-op-seq', 'mbom-op-name', 'mbom-op-desc'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    ['mbom-op-labor', 'mbom-op-machine', 'mbom-op-parent'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    ['mbom-op-setup', 'mbom-op-cycle'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '0';
    });
  }

  showAddOpModal() {
    this._resetOpForm();
    document.getElementById('mbom-op-dialog-title').innerHTML =
      '<i class="fas fa-plus"></i> Add Operation';
    const parentField = document.getElementById('mbom-op-parent-field');
    if (parentField) parentField.style.display = '';
    this._openDialog('mbom-op-backdrop');
  }

  showAddSubOpModal(parentPk) {
    this._resetOpForm();
    document.getElementById('mbom-op-dialog-title').innerHTML =
      '<i class="fas fa-level-down-alt"></i> Add Sub-Step';
    const parentSel = document.getElementById('mbom-op-parent');
    if (parentSel) parentSel.value = parentPk;
    const parentField = document.getElementById('mbom-op-parent-field');
    if (parentField) parentField.style.display = 'none'; // auto-set, hide to simplify
    this._openDialog('mbom-op-backdrop');
  }

  async showEditOpModal(opId) {
    try {
      const op = await this.api(`/operation/${opId}/`);
      document.getElementById('mbom-op-dialog-title').innerHTML =
        '<i class="fas fa-edit"></i> Edit Operation';
      document.getElementById('mbom-op-id').value          = op.pk;
      document.getElementById('mbom-op-seq').value         = op.sequence_number;
      document.getElementById('mbom-op-name').value        = op.name;
      document.getElementById('mbom-op-desc').value        = op.description || '';
      document.getElementById('mbom-op-parent').value      = op.parent_operation || '';
      document.getElementById('mbom-op-labor').value       = op.labor_rate || '';
      document.getElementById('mbom-op-machine').value     = op.machine_center || '';
      document.getElementById('mbom-op-setup').value       = op.setup_time_minutes;
      document.getElementById('mbom-op-cycle').value       = op.run_time_per_unit_minutes;
      const parentField = document.getElementById('mbom-op-parent-field');
      if (parentField) parentField.style.display = '';
      this._openDialog('mbom-op-backdrop');
    } catch (e) {
      this.toast(`Failed to load operation: ${e.message}`, 'error');
    }
  }

  async saveOp() {
    const opId = document.getElementById('mbom-op-id').value;
    const seq  = document.getElementById('mbom-op-seq').value.trim();
    const name = document.getElementById('mbom-op-name').value.trim();

    if (!seq || !name) {
      this.toast('Sequence and name are required', 'error');
      return;
    }

    // If no routing yet, we need to create one first and reload
    if (!this.routingId) {
      try {
        await this.api('/routing/', {
          method: 'POST',
          body: JSON.stringify({ part: this.partId, standard_batch_size: this.batchSize }),
        });
        this.toast('Routing created â€” reloadingâ€¦', 'info');
        this._closeDialogs();
        setTimeout(() => location.reload(), 600);
        return;
      } catch (e) {
        this.toast(`Failed to create routing: ${e.message}`, 'error');
        return;
      }
    }

    const payload = {
      routing:                  this.routingId,
      sequence_number:          seq,
      name:                     name,
      description:              document.getElementById('mbom-op-desc').value,
      parent_operation:         document.getElementById('mbom-op-parent').value || null,
      labor_rate:               document.getElementById('mbom-op-labor').value   || null,
      machine_center:           document.getElementById('mbom-op-machine').value || null,
      setup_time_minutes:       document.getElementById('mbom-op-setup').value   || '0',
      run_time_per_unit_minutes:document.getElementById('mbom-op-cycle').value   || '0',
    };

    const btn = document.getElementById('mbom-op-save-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="mbom-spinner"></span> Savingâ€¦';

    try {
      if (opId) {
        await this.api(`/operation/${opId}/`, { method: 'PATCH', body: JSON.stringify(payload) });
        this.toast('Operation updated');
      } else {
        await this.api('/operation/', { method: 'POST', body: JSON.stringify(payload) });
        this.toast('Operation added');
      }
      this._closeDialogs();
      await this.loadOperations();
      await this.loadCostSummary();
    } catch (e) {
      this.toast(`Save failed: ${e.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-save"></i> Save';
    }
  }

  // =========================================================
  // Delete Operation
  // =========================================================
  async deleteOp(opId) {
    const op = this._findOp(opId);
    const name = op ? op.name : `#${opId}`;
    const subCount = (op?.sub_operations || []).length;

    const msg = subCount > 0
      ? `Delete "${name}" and its ${subCount} sub-step(s)?`
      : `Delete "${name}"?`;

    if (!confirm(msg)) return;

    try {
      await this.api(`/operation/${opId}/`, { method: 'DELETE' });
      this.toast('Operation deleted');
      await this.loadOperations();
      await this.loadCostSummary();
    } catch (e) {
      this.toast(`Delete failed: ${e.message}`, 'error');
    }
  }

  // =========================================================
  // Batch size update
  // =========================================================
  async updateBatchSize() {
    const newSize = parseInt(document.getElementById('mbom-batch-input')?.value) || 1;
    if (!this.routingId) { this.toast('No routing to update', 'error'); return; }

    try {
      await this.api(`/routing/${this.routingId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ standard_batch_size: newSize }),
      });
      this.batchSize = newSize;
      this.toast(`Batch size updated to ${newSize}`);
      await this.loadCostSummary();
    } catch (e) {
      this.toast(`Failed: ${e.message}`, 'error');
    }
  }

  // =========================================================
  // Bootstrap
  // =========================================================
  async init() {
    // Close dialogs on backdrop click
    document.querySelectorAll('.mbom-backdrop').forEach(bd => {
      bd.addEventListener('click', e => {
        if (e.target === bd) this._closeDialogs();
      });
    });

    // Global reference for inline onclick handlers
    window._mbomPanel = this;

    await Promise.all([
      this.loadCostSummary(),
      this.loadOperations(),
    ]);
  }
}

// Auto-boot: panel config is injected by the template into window.MBOM_CONFIG
document.addEventListener('DOMContentLoaded', () => {
  if (window.MBOM_CONFIG) {
    const panel = new MbomPanel(window.MBOM_CONFIG);
    panel.init();
  }
});


// =========================================================
// PUI React Integration Exports
// =========================================================
export function renderMbomPanel(target, context) {
  if (!target) return;
  const partId = context?.target_id || context?.id;
  target.setAttribute('data-mbom-panel', 'true');

  if (!document.getElementById('mbom-css')) {
    const link = document.createElement('link');
    link.id = 'mbom-css';
    link.rel = 'stylesheet';
    link.href = '/static/plugins/inventree-mbom/inventree_mbom/css/mbom.css';
    document.head.appendChild(link);
  }

  target.innerHTML = '<div style=\"padding:16px;font-family:system-ui,-apple-system,sans-serif;\">' +
    '<div style=\"display:flex;align-items:center;gap:10px;margin-bottom:12px;\">' +
      '<span style=\"font-size:1.5rem;\">⚙️</span>' +
      '<div>' +
        '<strong style=\"font-size:1.1rem;\">Manufacturing Routing (mBOM)</strong>' +
        '<div style=\"font-size:0.8rem;color:#6b7280;\">Hierarchical Process Routing &amp; Operational Costs</div>' +
      '</div>' +
    '</div>' +
    '<div id=\"mbom-target-loading\" style=\"padding:20px;text-align:center;color:#6b7280;\">Loading routing...</div>' +
  '</div>';

  fetch('/plugin/inventree-mbom/panel/part/' + partId + '/', {
    headers: { 'Accept': 'text/html, */*' }
  })
    .then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    })
    .then(function(html) {
      target.innerHTML = html;
      if (window.MBOM_CONFIG) {
        const panel = new MbomPanel(window.MBOM_CONFIG);
        panel.init();
      }
    })
    .catch(function(err) {
      target.innerHTML = '<div style=\"padding:16px;color:#dc2626;background:#fee2e2;border-radius:8px;\">' +
        '<strong>Error loading mBOM panel:</strong> ' + err.message +
      '</div>';
    });
}

export function renderMbomPricingPanel(target, context) {
  if (!target) return;
  const partId = context?.target_id || context?.id;
  target.setAttribute('data-mbom-pricing-panel', 'true');

  target.innerHTML = '<div style=\"padding:12px;color:#6b7280;\">Loading pricing...</div>';

  fetch('/plugin/inventree-mbom/pricing-panel/' + partId + '/', {
    headers: { 'Accept': 'text/html, */*' }
  })
    .then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    })
    .then(function(html) {
      target.innerHTML = html;
    })
    .catch(function(err) {
      target.innerHTML = '<div style=\"padding:12px;color:#dc2626;\">Error: ' + err.message + '</div>';
    });
}