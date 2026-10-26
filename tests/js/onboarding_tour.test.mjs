import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const src = readFileSync(new URL('../../web/app/onboarding_tour.js', import.meta.url), 'utf8');

function tourContext() {
    const context = {
        document: { getElementById: () => null, addEventListener: () => {} },
        window: { addEventListener: () => {}, innerWidth: 360, innerHeight: 640 },
        map: { on: () => {} },
        HTMLElement: class {},
        localStorage: { getItem: () => null, setItem: () => {} },
        requestAnimationFrame: () => 1,
        cancelAnimationFrame: () => {},
    };
    vm.createContext(context);
    vm.runInContext(src, context);
    return context;
}

test('tour script is valid native JavaScript with no third-party runtime', () => {
    assert.doesNotThrow(() => new vm.Script(src));
    assert.doesNotMatch(src, /fetch\(|apiPostJson\(|submitReportPdf\(|chooseFieldPhotoLocation\(/);
});

test('intro and outro remain possible without vehicle data', () => {
    const context = tourContext();
    const steps = vm.runInContext('onboardingTourSteps(null).map(step => step.title)', context);
    assert.equal(steps[0], 'tour.welcomeTitle');
    assert.equal(steps.at(-1), 'tour.doneTitle');
    assert.ok(steps.includes('tour.layersTitle'));
    assert.ok(steps.includes('tour.addTitle'));
    assert.ok(!steps.includes('tour.reportTitle'));
});

test('real report and vehicle card only appear if there is an example marker', () => {
    const context = tourContext();
    const steps = vm.runInContext('onboardingTourSteps({}).map(step => step.title)', context);
    assert.ok(steps.includes('tour.vehicleTitle'));
    assert.ok(steps.includes('tour.reportTitle'));
    assert.ok(steps.includes('tour.sourcesTitle'));
});

test('placement keeps the tooltip inside narrow mobile viewport', () => {
    const context = tourContext();
    const rect = { left: 8, right: 330, top: 40, bottom: 115, width: 322, height: 75 };
    context.testRect = rect;
    const result = vm.runInContext('onboardingTourPlacement(testRect, {width: 320,height: 190},360,640)', context);
    assert.ok(result.left >= 12);
    assert.ok(result.left + 320 <= 348);
    assert.ok(result.top >= 12);
    assert.ok(result.top + 190 <= 628);
});

test('placement prefers above when there is no space below', () => {
    const context = tourContext();
    const result = vm.runInContext(
        'onboardingTourPlacement({left:200,right:245,top:565,bottom:609,width:45,height:44},{width:200,height:155},420,650)',
        context,
    );
    assert.ok(result.top + 155 < 565);
});

test('centered welcome dialog is clamped inside the viewport', () => {
    const context = tourContext();
    const result = vm.runInContext('onboardingTourPlacement(null, {width:344,height:240},375,667)', context);
    assert.ok(result.left > 0);
    assert.ok(result.top > 0);
    assert.ok(result.left + 344 <= 375);
});
