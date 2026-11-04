// Public WowCube game API: generated from the engine sources (api/SOURCE).
// Only what a game compiled as a cube module (OCT_APP_MODULE) uses. Do not edit: regenerate.
#pragma once
#include <stdint.h>
#include "oct_app_version.h"    //OCT_APP_SEMVER, the layout of octPackHeader_t.AppVersion

#define OCT_SOFTWARE_NAME_MAXLEN 80
#define OCT_ASSET_NAME_MAXLEN 24
#define OCT_ASSETS_CAP  5120u                                       //Upper bound for assets (could be raised at the cost of shrinking assets memory)
