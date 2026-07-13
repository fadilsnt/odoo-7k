/** @odoo-module **/

let activePivotController = null;

export function setActivePivotController(controller) {
    activePivotController = controller;
}

export function getActivePivotController() {
    return activePivotController;
}
