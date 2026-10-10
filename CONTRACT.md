# Warpspeed CONTRACT
(Only the project owner edits this file. Code must follow it exactly.)

## Constants (config.py)
ROLES: owner, store, supervisor, qc, buyer
ORDER_STATUS: NEW, WEAVING, DYEING, QC, READY, DISPATCHED
MACHINE_TYPE: SPINNING, WEAVING, DYEING
MACHINE_STATUS: RUNNING, IDLE, BREAKDOWN
MOVEMENT_TYPE: RECEIPT, RESERVE, RELEASE, CONSUME
QC_STATUS: PENDING, PASS, REWORK, REJECT
WORK_STATUS: PENDING, RUNNING, DONE
STAGES: WEAVING, DYEING (DYEING is final; rolls are cut there)
ROLL_LENGTH_M=50, WASTAGE=0.08
FABRIC_RECIPES = {fabric_type: [(material_name, kg_per_meter), ...]}
Settings keys: wage_rate=120, overhead_rate=50

## Transaction rule
Write services take commit=True. A service calling another service's write
inside its own transaction passes commit=False and commits once at the end.
Errors are ValueError("clear message"). Routes catch ValueError and flash it.

## Endpoints (blueprint /prefix: endpoints)
auth: auth.login, auth.logout
dashboard /dashboard: index, reset
inventory /inventory: index, receive
orders /orders: index, new, detail(order_id), confirm(order_id)
production /production: index, board (HTMX partial), start, log, breakdown,
  repair, simulate_start, simulate_stop, simulate_tick
quality /quality: index, set_status, trace(code), recall, qr(code)
dispatch /dispatch: index, create, invoice_pdf(invoice_id)
wages /wages: index, mark
buyer /portal: index, order_card(order_id) (HTMX partial)
Templates: templates/<blueprint>/..., extend base.html, block content.
Partials start with underscore.

## Role access (auth.role_required(*roles))
owner: everything and reset | store: inventory, orders, dispatch
supervisor: production, orders | qc: quality | buyer: portal only

## Services
inventory: receive_stock(material_id, qty, lot_no, supplier_id, unit_cost,
 order_id=None, commit=True); on_hand/reserved/available(material_id)->float;
 low_stock_materials()->[Material]; stock_summary()->[{material_id,name,colour,
 on_hand,reserved,available,reorder_level,low}];
 consume_for_order(order_id, commit=True)->first yarn lot_no
orders: calculate_bom(fabric_type, meters)->[(material_id,kg)];
 create_order(buyer_id,fabric_type,colour,meters,price_per_meter,deadline)->Order;
 check_availability(order_id)->{can_start,shortages:[{material_id,name,short_by_kg}]};
 confirm_order(order_id, commit=True); order_status(order_id)->ORDER_STATUS
production: start_work_order(order_id,machine_id,stage,commit=True)->WorkOrder;
 log_output(work_order_id,meters,commit=True)->WorkOrder;
 report_breakdown(machine_id); repair_machine(machine_id);
 delay_risk(order_id)->{at_risk,projected,days_late};
 machine_board()->[{machine_id,name,type,status,order_id,stage,progress_pct,today_m}]
qc: set_qc(roll_id,status,defect_type=None,commit=True); qc_queue()->[FabricRoll];
 trace_roll(code)->{roll,order,buyer,machine,yarn_lot,dispatch};
 lot_recall(lot_no)->{rolls,buyers,buyer_count}; roll_qr_png(code)->bytes
dispatch: available_rolls(buyer_id)->[FabricRoll];
 create_dispatch(buyer_id,truck_no,roll_ids,commit=True)->Dispatch (+Invoice);
 invoice_pdf(invoice_id)->bytes; finished_stock()->[FabricRoll]
costing: order_cost(order_id)->{yarn,wages,overhead,total,passed_meters,
 cost_per_meter,margin_per_meter,yield_variance,formula};
 wages_total(year,month); monthly_pnl(year,month)->{revenue,material_cost,
 wages,overhead,profit}; machine_output(year,month)->[{machine,meters}]
