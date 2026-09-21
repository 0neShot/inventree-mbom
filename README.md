# inventree-mbom

**Manufacturing BOM & Routings plugin for [InvenTree](https://inventree.org)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![InvenTree](https://img.shields.io/badge/InvenTree-%3E%3D1.3.1-blue)](https://inventree.org)

---

## Overview

`inventree-mbom` extends InvenTree with a full **Manufacturing BOM (mBOM)** capability, adding a dedicated **"Manufacturing Routing (mBOM)"** tab to every assembly part. It supports:

- **Hierarchical process steps** (Op 10 → 10.1 Stencil → 10.2 Pick & Place → 10.3 Reflow)
- **Central labor and machine rate catalog** with dynamic cost propagation
- **Reusable process templates** that can be applied to any assembly in one click
- **Setup Time (fixed/batch)** + **Run/Cycle Time (per unit)** tracked separately
- **CO₂ emission factor** tracking per machine center
- **Full pricing integration**: manufacturing costs bridge into InvenTree's native `PartPricing` system
<img width=80% height=80% alt="grafik" src="https://github.com/user-attachments/assets/b6abd213-604c-44b7-9c04-36740a2acd2e" />

---

## Features

### Central Tariff Catalog

| Model | Fields |
|---|---|
| `LaborRate` | Name, hourly rate, currency, description |
| `MachineCenter` | Name, hourly rate, currency, CO₂ factor/min |

### Process Templates

Create reusable templates (e.g. "SMT Assembly Standard") with hierarchical steps. Apply them to any assembly with one click.
<img width=80% height=80% alt="grafik" src="https://github.com/user-attachments/assets/b3ede2a2-b035-4d7a-ae7d-4abaccdbec72" />

### Part Routing (mBOM)

Each assembly gets a `PartRouting` containing `RoutingOperation` instances:

```
PartRouting (for Part: Widget PCB)
├── Op 10: SMT Assembly         [Labor: Assembler, Setup: 30min, Cycle: 2min/unit]
│   ├── Op 10.1: Stencil Paste
│   ├── Op 10.2: Pick & Place
│   └── Op 10.3: Reflow
└── Op 20: Final Inspection     [Labor: Engineer, Cycle: 5min/unit]
```

### Cost Formula

```
Total Operation Cost (batch) = (Setup_min × Rate/min) + (Cycle_min/unit × Rate/min × batch_qty)
Per-Unit Cost = Total Cost ÷ batch_size
Total Assembly Cost = eBOM Material Cost + mBOM Labor Cost + mBOM Machine Cost
```

### Pricing Bridge

When a `LaborRate` or `MachineCenter` hourly rate is updated, Django `post_save` signals automatically call `PartPricing.schedule_for_update()` on all affected assemblies — **no InvenTree core modifications required**.
<img width=50% height=50% alt="grafik" src="https://github.com/user-attachments/assets/bcbeb5af-5454-4374-81ce-b48354539c9e" />

---

## Setup

* **Install** Install this plugin in the webinterface with the packagename `inventree-mbom`
* **Enable** Enable the plugin in the plugin settings. You need to be signed in as a superuser for this. The server will restart if you enable the plugin
* **Configure** There are no configuration options for this plugin. Your server needs to have URL and App mixins enabled.
<img width=40% height=40% alt="grafik" src="https://github.com/user-attachments/assets/849841a1-b0fc-4863-a2f4-78fe525c502a" />

---

## REST API Endpoints

All endpoints are under `/plugin/inventree-mbom/`:

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `labor-rate/` | List/Create labor rates |
| GET/PUT/DELETE | `labor-rate/<pk>/` | Retrieve/Update/Delete labor rate |
| GET/POST | `machine-center/` | List/Create machine centers |
| GET/PUT/DELETE | `machine-center/<pk>/` | Retrieve/Update/Delete machine center |
| GET/POST | `process-template/` | List/Create process templates |
| GET/POST | `process-template-step/` | List/Create template steps |
| GET/POST | `routing/` | List/Create part routings |
| GET/PUT/DELETE | `routing/<pk>/` | Retrieve/Update/Delete routing |
| GET/POST | `operation/` | List/Create routing operations |
| GET/PUT/DELETE | `operation/<pk>/` | Retrieve/Update/Delete operation |
| POST | `apply-template/` | Apply a template to a part's routing |
| GET | `cost-summary/<part_pk>/` | Full cost breakdown for a part |

---

## Running Tests

```bash
# From InvenTree root:
python manage.py test inventree_mbom
```

---

## Architecture & Design Decisions

### Why Not a Standalone SPA?
This plugin uses InvenTree's native `UserInterfaceMixin` + `PanelMixin` pattern to inject the mBOM tab. The panel renders server-side HTML with vanilla JS for API interactions, matching InvenTree's native look & feel without requiring a separate build pipeline.

### Pricing Bridge Strategy
InvenTree's `PartPricing.bom_cost` only rolls up physical BOM items. Rather than patching InvenTree core, this plugin uses Django's `post_save` signal on `LaborRate`/`MachineCenter` to call `PartPricing.schedule_for_update()` on affected parts. The cost summary API endpoint provides the full breakdown (material + labor + machine) for display in the UI panel.

### Template vs. Instance Pattern
Process Templates are reusable blueprints. When applied to a part, operations are **copied** (not linked) so engineers can customize times/notes per-part without mutating the global template. The `source_template` FK is informational only.

---

## License

MIT License - see [LICENSE](LICENSE)
