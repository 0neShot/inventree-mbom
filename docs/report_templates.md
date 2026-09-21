# Using mBOM Data in InvenTree Report Templates

The `inventree-mbom` plugin exposes manufacturing routing operations, labor costs, machine center tariffs, setup/run times, and carbon footprint metrics natively to InvenTree's Django Report & Label rendering engine (WeasyPrint).

---

## 1. How InvenTree Report Templates Work

InvenTree renders PDF reports using Django's template engine. When printing a report, InvenTree passes the target model instance into the template context:

| Report Model Type | Primary Context Variable | How to Access mBOM Routing |
| :--- | :--- | :--- |
| **Part** (`part`) | `part` | `part.mbom_routing` |
| **Build Order** (`build`) | `build` | `build.part.mbom_routing` |
| **BOM Item** (`bomitem`) | `bom_item` | `bom_item.sub_part.mbom_routing` |
| **Stock Item** (`stockitem`) | `stock_item` | `stock_item.part.mbom_routing` |

> [!TIP]
> If a part does not have an mBOM routing defined, Django evaluates `part.mbom_routing` as falsy without raising an error. Always wrap routing sections with `{% if part.mbom_routing %}` to handle parts without routings gracefully.

---

## 2. Available Variables, Properties & Methods

### `part.mbom_routing` (PartRouting)

| Field / Property / Method | Description | Sample Output |
| :--- | :--- | :--- |
| `routing.standard_batch_size` | Standard batch quantity used to amortise setup costs | `50` |
| `routing.notes` | Process, safety, or quality instructions text | `"Wear ESD wrist strap..."` |
| `routing.source_template.name` | Seed template name (if applied from a template) | `"SMT PCB Assembly Standard"` |
| `routing.updated` | Last modification datetime | `2026-09-21 10:15:00` |
| `routing.updated_by` | User instance who last changed the routing | `admin` |
| `routing.top_level_operations` | Queryset of top-level operations (excluding nested sub-steps), ordered by sequence | `[Op 10, Op 20, ...]` |
| `routing.all_operations` | Queryset of all operations including sub-steps, ordered by sequence | `[Op 10, Op 10.1, ...]` |
| `routing.total_setup_time_minutes` | Sum of all setup times in minutes across all operations | `60.0` |
| `routing.total_run_time_per_unit_minutes` | Sum of all cycle/run times per unit in minutes | `10.8` |
| `routing.total_labor_cost` | Total labor cost for the standard batch size | `345.50` |
| `routing.total_machine_cost` | Total machine operating cost for the standard batch size | `397.79` |
| `routing.total_manufacturing_cost` | Total manufacturing cost (`total_labor_cost + total_machine_cost`) | `743.29` |
| `routing.per_unit_manufacturing_cost` | Manufacturing cost amortised per unit (`total / standard_batch_size`) | `24.78` |
| `routing.total_co2_kg` | Total estimated CO₂ emissions in kilograms for the batch | `0.090000` |
| `routing.used_labor_rates` | Distinct `LaborRate` objects utilized across all operations in this routing | `[LaborRate: Assembler, ...]` |
| `routing.used_machine_centers` | Distinct `MachineCenter` objects utilized across all operations in this routing | `[MachineCenter: Reflow Oven, ...]` |

---

### `operation` (RoutingOperation)

When iterating through `routing.top_level_operations` or `routing.all_operations`:

| Field / Property / Method | Description | Sample Output |
| :--- | :--- | :--- |
| `op.sequence_number` | Operation sequence identifier | `"10"`, `"20.1"` |
| `op.name` | Operation title | `"SMT Component Placement"` |
| `op.description` | Detailed tool notes or work instructions | `"Use nozzle #4 on pick & place"` |
| `op.labor_rate.name` | Assigned labor classification name | `"Assembler"` |
| `op.labor_rate.hourly_rate` | Hourly labor rate in EUR/currency | `27.98` |
| `op.machine_center.name` | Assigned machine/workcenter name | `"SMT Pick & Place"` |
| `op.machine_center.hourly_rate`| Hourly machine operating rate | `60.00` |
| `op.setup_time_minutes` | Fixed setup time in minutes for this step | `30.0` |
| `op.run_time_per_unit_minutes` | Unit cycle/run time in minutes | `0.45` |
| `op.labor_setup_cost` | Fixed labor cost for setup | `13.99` |
| `op.labor_run_cost_per_unit` | Unit labor cost | `0.21` |
| `op.machine_setup_cost` | Fixed machine cost for setup | `30.00` |
| `op.machine_run_cost_per_unit` | Unit machine cost | `0.45` |
| `op.labor_cost` | Total labor cost amortised over batch size | `24.48` |
| `op.machine_cost` | Total machine cost amortised over batch size | `52.50` |
| `op.total_cost` | Total operation cost (`labor_cost + machine_cost`) | `76.98` |
| `op.per_unit_cost` | Operation cost per unit produced | `2.57` |
| `op.co2_kg` | CO₂ emissions in kg for this operation | `0.045000` |
| `op.sub_operations.all` | Nested sub-operations belonging to this operation | `[Op 10.1, Op 10.2]` |

---

## 3. Minimal Example: Embedding mBOM Cost into an Existing Report

Add this snippet to your existing Part or Build report template:

```html
{% if part.mbom_routing %}
<div class="mbom-summary-box" style="border: 1px solid #dee2e6; padding: 10px; margin-top: 15px; border-radius: 4px;">
  <h3 style="margin-top:0;">Manufacturing Costs (mBOM)</h3>
  <p>
    <strong>Standard Batch:</strong> {{ part.mbom_routing.standard_batch_size }} units |
    <strong>Total Setup Time:</strong> {{ part.mbom_routing.total_setup_time_minutes|floatformat:1 }} min |
    <strong>Unit Run Time:</strong> {{ part.mbom_routing.total_run_time_per_unit_minutes|floatformat:1 }} min/unit
  </p>
  <p>
    <strong>Unit Mfg Cost:</strong> {{ part.mbom_routing.per_unit_manufacturing_cost|floatformat:2 }} EUR
    (Labor: {{ part.mbom_routing.total_labor_cost|floatformat:2 }} EUR, Machine: {{ part.mbom_routing.total_machine_cost|floatformat:2 }} EUR)
  </p>
</div>
{% endif %}
```

---

## 4. Full Production Sample: Shop-Floor Traveler Report

A complete, production-ready manufacturing traveler and routing template is bundled with this plugin at:
`inventree_mbom/templates/inventree_mbom/reports/mbom_routing_traveler_report.html`

It provides:
- **A4 Portrait Layout** with clean WeasyPrint PDF pagination.
- **Part Overview**: IPN, Description, Revision, and Batch Size.
- **Manufacturing KPI Cards**: Setup time, unit cycle time, total labor, total machine cost, and unit manufacturing cost.
- **Hierarchical Routing Table**: Sequence numbers, operation instructions, labor tariffs, machine centers, setup/run times, unit cost, and a physical sign-off box for shop-floor operators.
- **Process & Quality Notes**: Renders any custom instructions or safety protocols attached to the routing.

---

## 5. How to Install the Report Template in InvenTree

1. Open your InvenTree web interface.
2. Navigate to **Settings -> System Settings -> Report Templates** (or search "Report Templates" in InvenTree settings).
3. Click **New Report Template**.
4. Configure the template:
   - **Template Name**: `Manufacturing Traveler & Routing`
   - **Model Type**: Select `Part` (or `Build Order`)
   - **File**: Upload [`mbom_routing_traveler_report.html`](../inventree_mbom/templates/inventree_mbom/reports/mbom_routing_traveler_report.html)
   - **Page Size**: `A4`
   - **Orientation**: `Portrait`
   - **Enabled**: `Checked`
5. Save the template.
6. Open any assembly part page (e.g. `/web/part/347`), click the **Reports** / **Print** button in the page toolbar, and select **Manufacturing Traveler & Routing** to download your PDF!
