/** @file Release Happy DOM once when opt-in suites share Bun's process. */
import {GlobalRegistrator} from '@happy-dom/global-registrator';

const {ISHIBAN_BROWSER_TESTS: browserTestSwitch} = Bun.env;
export const isBrowserEnabled = browserTestSwitch === '1';

if (isBrowserEnabled && GlobalRegistrator.isRegistered) {
  await GlobalRegistrator.unregister();
}
