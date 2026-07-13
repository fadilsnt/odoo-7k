/** @odoo-module **/

function debugDump(label, obj) {
    try {
        console.warn(`[ai_pivot_filter] ${label}`, obj);
    } catch (e) {
    }
}

export function readLivePivotState(controller) {
    if (!controller) {
        return null;
    }
    const model = controller.model;
    const metaData = model && model.metaData;

    if (!metaData) {
        debugDump("controller.model has no metaData:", model);
        return null;
    }

    const resModel = metaData.resModel || (controller.props && controller.props.resModel) || null;

    let activeMeasures = null;
    if (Array.isArray(metaData.activeMeasures)) {
        activeMeasures = [...metaData.activeMeasures];
    } else {
        debugDump("metaData.activeMeasures not found/array, metaData was:", metaData);
    }

    let allMeasures = null;
    if (metaData.measures && typeof metaData.measures === "object") {
        allMeasures = Object.keys(metaData.measures);
    }

    let domain = [];
    try {
        if (controller.env && controller.env.searchModel && controller.env.searchModel.domain) {
            domain = controller.env.searchModel.domain;
        }
    } catch (e) {
        debugDump("could not read env.searchModel.domain:", e);
    }

    let rowGroupBy = null;
    if (Array.isArray(metaData.rowGroupBys)) {
        rowGroupBy = [...metaData.rowGroupBys];
    } else {
        debugDump("metaData.rowGroupBys not found/array, metaData was:", metaData);
    }

    let colGroupBy = null;
    if (Array.isArray(metaData.colGroupBys)) {
        colGroupBy = [...metaData.colGroupBys];
    } else {
        debugDump("metaData.colGroupBys not found/array, metaData was:", metaData);
    }

    return { resModel, activeMeasures, allMeasures, domain, rowGroupBy, colGroupBy };
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function applyDomainViaSearchBar(controller, newDomain) {
    if (!controller || !Array.isArray(newDomain)) {
        return false;
    }
    const searchModel = controller.env && controller.env.searchModel;
    if (!searchModel || typeof searchModel.createNewFilters !== "function") {
        debugDump("searchModel.createNewFilters not available, searchModel was:", searchModel);
        return false;
    }

    try {
        if (typeof searchModel.clearQuery === "function") {
            searchModel.clearQuery();
        }
        if (newDomain.length > 0) {
            searchModel.createNewFilters([
                {
                    description: "Filter AI",
                    domain: JSON.stringify(newDomain),
                },
            ]);
        }
        for (let i = 0; i < 20; i++) {
            await sleep(100);
            try {
                if (domainsEqualLoose(searchModel.domain, newDomain)) {
                    break;
                }
            } catch (e) {
                break;
            }
        }
        if (controller.render && typeof controller.render === "function") {
            controller.render();
        }
        return true;
    } catch (e) {
        debugDump("error while applying domain via search bar:", e);
        return false;
    }
}

function domainsEqualLoose(a, b) {
    try {
        return JSON.stringify(a || []) === JSON.stringify(b || []);
    } catch (e) {
        return false;
    }
}

export async function applyLiveDomainPrivate(controller, newDomain) {
    if (!controller || !Array.isArray(newDomain)) {
        return false;
    }
    const model = controller.model;

    if (!model || typeof model.load !== "function") {
        debugDump("cannot apply domain, model.load is not a function, model was:", model);
        return false;
    }

    try {
        const metaData = model.metaData;
        if (metaData && typeof metaData === "object") {
            metaData.domain = newDomain;
        }

        const baseSearchParams =
            model.searchParams && typeof model.searchParams === "object" ? model.searchParams : {};
        const newSearchParams = { ...baseSearchParams, domain: newDomain };
        await model.load(newSearchParams);
        model.searchParams = newSearchParams;
        if (typeof controller.render === "function") {
            controller.render();
        }
        return true;
    } catch (e) {
        debugDump("error while applying live domain (private fallback):", e);
        return false;
    }
}

export async function applyLiveGroupBy(controller, { rowGroupBy, colGroupBy } = {}) {
    if (!controller) {
        return false;
    }
    if (!Array.isArray(rowGroupBy) && !Array.isArray(colGroupBy)) {
        return true;
    }
    const model = controller.model;
    const metaData = model && model.metaData;

    if (!metaData || !Array.isArray(metaData.rowGroupBys) || !Array.isArray(metaData.colGroupBys)) {
        debugDump("cannot apply groupby, metaData.rowGroupBys/colGroupBys missing:", metaData);
        return false;
    }
    if (typeof model.load !== "function") {
        debugDump("cannot apply groupby, model.load is not a function, model was:", model);
        return false;
    }

    const previousRowGroupBys = [...metaData.rowGroupBys];
    const previousColGroupBys = [...metaData.colGroupBys];

    try {
        if (Array.isArray(rowGroupBy)) {
            metaData.rowGroupBys = [...rowGroupBy];
        }
        if (Array.isArray(colGroupBy)) {
            metaData.colGroupBys = [...colGroupBy];
        }
        await model.load(model.searchParams || {});
        if (typeof controller.render === "function") {
            controller.render();
        }
        return true;
    } catch (e) {
        metaData.rowGroupBys = previousRowGroupBys;
        metaData.colGroupBys = previousColGroupBys;
        debugDump("error while applying live groupby:", e);
        return false;
    }
}

export function applyLiveMeasures(controller, desiredMeasures) {
    if (!controller || !Array.isArray(desiredMeasures)) {
        return false;
    }
    const model = controller.model;
    const metaData = model && model.metaData;

    if (!metaData || !Array.isArray(metaData.activeMeasures)) {
        debugDump("cannot apply measures, metaData/activeMeasures missing:", metaData);
        return false;
    }
    if (typeof model.toggleMeasure !== "function") {
        debugDump("model.toggleMeasure is not a function, model was:", model);
        return false;
    }

    const current = [...metaData.activeMeasures];
    const toAdd = desiredMeasures.filter((m) => !current.includes(m));
    const toRemove = current.filter((m) => !desiredMeasures.includes(m));

    try {
        for (const measure of toAdd) {
            model.toggleMeasure(measure);
        }
        for (const measure of toRemove) {
            model.toggleMeasure(measure);
        }
        if (typeof controller.render === "function") {
            controller.render();
        }
        return true;
    } catch (e) {
        debugDump("error while toggling measures:", e);
        return false;
    }
}
