// Can record_html.mjs (next to this file) record? Playwright is never installed into the plugin folder: both
// scripts resolve it, in this order, from
//   1. $WOWCUBE_NODE_DIR            (an npm prefix: the folder holding node_modules, or node_modules itself)
//   2. ~/.wowcube/node              (npm i --prefix ~/.wowcube/node playwright: the recommended place)
//   3. the workspace                (the current folder or a parent with node_modules)
//   4. this script's folder         (an older install; a global npm install never counts)
// and that Playwright's Chromium must exist.
// Prints one line (the Chromium path and where Playwright came from, or why not) and exits 0 ready, 2 no Playwright,
// 3 no Chromium. Used by scripts/check_env.ps1 / check_env.sh; it reads only, installs nothing.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createRequire } = require('module');

function playwrightDirs() {
  const dirs = [];
  if (process.env.WOWCUBE_NODE_DIR) dirs.push(path.resolve(process.env.WOWCUBE_NODE_DIR));
  dirs.push(path.join(os.homedir(), '.wowcube', 'node'));
  dirs.push(process.cwd());
  dirs.push(__dirname);
  return dirs;
}

function loadPlaywright() {
  for (const dir of playwrightDirs()) {
    try {
      // a require rooted in <dir> looks in <dir>/node_modules and its parents, like a script stored there
      return { pw: createRequire(path.join(dir, 'resolve-playwright.js'))('playwright'), from: dir };
    } catch (e) {
      if (e && e.code !== 'MODULE_NOT_FOUND') throw e;
    }
  }
  return null;
}

module.exports = { playwrightDirs, loadPlaywright };

if (require.main === module) {
  const found = loadPlaywright();
  if (!found) {
    console.log('playwright does not resolve from ' + playwrightDirs().join(', '));
    process.exit(2);
  }
  let exe = '';
  try {
    exe = found.pw.chromium.executablePath();
  } catch (e) {
    exe = '';
  }
  if (exe && fs.existsSync(exe)) {
    console.log(exe + ' (playwright from ' + found.from + ')');
    process.exit(0);
  }
  console.log((exe ? 'Chromium missing: ' + exe : 'Chromium path unknown') + ' (playwright from ' + found.from + ')');
  process.exit(3);
}
