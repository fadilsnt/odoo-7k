/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { getActivePivotController } from "./ai_pivot_registry";
import {
    readLivePivotState,
    applyLiveMeasures,
    applyDomainViaSearchBar,
    applyLiveDomainPrivate,
    applyLiveGroupBy,
} from "./ai_pivot_bridge";

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function domainsEqual(a, b) {
    try {
        return JSON.stringify(a || []) === JSON.stringify(b || []);
    } catch (e) {
        return false;
    }
}

async function waitForFreshPivotController(previousController, resModel, { retries = 40, delayMs = 100 } = {}) {
    for (let i = 0; i < retries; i++) {
        const controller = getActivePivotController();
        if (
            controller &&
            controller !== previousController &&
            controller.model &&
            controller.model.metaData &&
            Array.isArray(controller.model.metaData.activeMeasures) &&
            (!resModel || controller.model.metaData.resModel === resModel)
        ) {
            return controller;
        }
        await sleep(delayMs);
    }
    return getActivePivotController();
}

export class AiPivotDialog extends Component {
    static template = "ai_pivot_filter.AiPivotDialog";
    static components = { Dialog };
    static props = {
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            text: "",
            loading: false,
        });
    }

    get controllerInfo() {
        const controller = this.action.currentController;
        return controller ? controller.action : null;
    }

    async onSend() {
        const text = (this.state.text || "").trim();
        if (!text) {
            return;
        }
        const actionInfo = this.controllerInfo;
        if (!actionInfo || !actionInfo.res_model) {
            this.notification.add("Tidak dapat mendeteksi model dari tampilan saat ini.", {
                type: "danger",
            });
            return;
        }

        this.state.loading = true;
        try {
            const pivotController = getActivePivotController();
            const liveState = readLivePivotState(pivotController);

            const resModel = actionInfo.res_model;
            const currentDomain = (liveState && liveState.domain) || actionInfo.domain || [];
            const currentMeasures = liveState && liveState.activeMeasures;
            const currentRowGroupBy = liveState && liveState.rowGroupBy;
            const currentColGroupBy = liveState && liveState.colGroupBy;

            if (!liveState) {
                this.notification.add(
                    "Tidak terdeteksi tampilan pivot yang aktif — measure/pengelompokan " +
                    "mungkin tidak bisa diterapkan secara langsung (hanya filter yang " +
                    "diterapkan).",
                    { type: "warning" }
                );
            }

            const result = await this.orm.call(
                "ai.pivot.assistant",
                "generate_pivot_state",
                [
                    resModel,
                    text,
                    currentDomain,
                    currentMeasures || null,
                    currentRowGroupBy || null,
                    currentColGroupBy || null,
                ]
            );

            const newDomain = (result && result.domain) || [];
            const newMeasures = result && Array.isArray(result.measures) ? result.measures : null;
            const newRowGroupBy = result && Array.isArray(result.row_groupby) ? result.row_groupby : null;
            const newColGroupBy = result && Array.isArray(result.col_groupby) ? result.col_groupby : null;

            const previousController = pivotController;
            const domainChanged = !domainsEqual(newDomain, currentDomain);
            const rowGroupByChanged = newRowGroupBy !== null && !domainsEqual(newRowGroupBy, currentRowGroupBy || []);
            const colGroupByChanged = newColGroupBy !== null && !domainsEqual(newColGroupBy, currentColGroupBy || []);
            const groupByChanged = rowGroupByChanged || colGroupByChanged;

            if (!domainChanged && !groupByChanged) {
                if (newMeasures !== null) {
                    if (!pivotController) {
                        this.notification.add(
                            "Tidak terdeteksi tampilan pivot yang aktif, measure tidak " +
                            "bisa diterapkan secara langsung.",
                            { type: "warning" }
                        );
                        this.props.close();
                        return;
                    }
                    const applied = applyLiveMeasures(pivotController, newMeasures);
                    if (!applied) {
                        this.notification.add(
                            "Measure tidak bisa diubah secara otomatis (struktur pivot " +
                            "tidak dikenali). Silakan atur measure manual lewat menu " +
                            "Pengukuran.",
                            { type: "warning" }
                        );
                        this.props.close();
                        return;
                    }
                    this.notification.add("Measure berhasil diperbarui oleh AI.", {
                        type: "success",
                    });
                } else {
                    this.notification.add(
                        "Tidak ada perubahan filter, pengelompokan, maupun measure " +
                        "yang terdeteksi dari instruksi tersebut.",
                        { type: "warning" }
                    );
                }
                this.props.close();
                return;
            }

            let liveApplied = false;
            if (pivotController) {
                let ok = true;
                if (domainChanged) {
                    ok = await applyDomainViaSearchBar(pivotController, newDomain);
                    if (!ok) {
                        ok = await applyLiveDomainPrivate(pivotController, newDomain);
                    }
                }
                if (ok && groupByChanged) {
                    ok =
                        ok &&
                        (await applyLiveGroupBy(pivotController, {
                            rowGroupBy: rowGroupByChanged ? newRowGroupBy : null,
                            colGroupBy: colGroupByChanged ? newColGroupBy : null,
                        }));
                }
                liveApplied = ok;
                if (liveApplied && domainChanged) {
                    try {
                        actionInfo.domain = newDomain;
                    } catch (e) {
                    }
                }
            }

            if (liveApplied) {
                if (newMeasures !== null) {
                    const applied = applyLiveMeasures(pivotController, newMeasures);
                    if (!applied) {
                        this.notification.add(
                            "Filter/pengelompokan diterapkan, tapi measure tidak bisa " +
                            "diubah secara otomatis (struktur pivot tidak dikenali). " +
                            "Silakan atur measure manual lewat menu Pengukuran.",
                            { type: "warning" }
                        );
                        this.props.close();
                        return;
                    }
                }
                this.notification.add(
                    "Filter, pengelompokan & measure berhasil diperbarui oleh AI.",
                    { type: "success" }
                );
                this.props.close();
                return;
            }

            const fallbackContext = { ...(actionInfo.context || {}) };
            if (rowGroupByChanged) {
                fallbackContext.pivot_row_groupby = newRowGroupBy;
            }
            if (colGroupByChanged) {
                fallbackContext.pivot_column_groupby = newColGroupBy;
            }
            if (newMeasures !== null) {
                fallbackContext.pivot_measures = newMeasures;
            }
            if (domainChanged) {
                for (const key of Object.keys(fallbackContext)) {
                    if (key.startsWith("search_default_")) {
                        delete fallbackContext[key];
                    }
                }
            }

            await this.action.doAction(
                {
                    ...actionInfo,
                    domain: newDomain,
                    context: fallbackContext,
                },
                { clear_breadcrumbs: true, stackPosition: "replaceCurrentAction" }
            );

            if (newMeasures !== null) {
                const freshController = await waitForFreshPivotController(previousController, resModel);
                const applied = applyLiveMeasures(freshController, newMeasures);
                if (!applied) {
                    this.notification.add(
                        "Filter/pengelompokan diterapkan, tapi measure tidak bisa " +
                        "diubah secara otomatis (struktur pivot tidak dikenali atau " +
                        "belum siap). Silakan atur measure manual lewat menu " +
                        "Pengukuran.",
                        { type: "warning" }
                    );
                    this.props.close();
                    return;
                }
            }

            this.notification.add(
                "Filter, pengelompokan & measure berhasil diperbarui oleh AI.",
                { type: "success" }
            );
            this.props.close();
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Terjadi kesalahan saat memproses permintaan AI.";
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}
