#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-${ROOT_DIR}/artifacts/mobile}"
PLATFORM="${1:-}"

prepare_platform() {
  local platform="$1"
  cd "${ROOT_DIR}"
  npm run mobile:prepare
  rm -rf "${platform}"
  npx cap add "${platform}"
}

package_android() {
  prepare_platform android
  (
    cd "${ROOT_DIR}/android"
    ./gradlew --no-daemon assembleDebug
  )
  mkdir -p "${ARTIFACT_DIR}"
  cp \
    "${ROOT_DIR}/android/app/build/outputs/apk/debug/app-debug.apk" \
    "${ARTIFACT_DIR}/NOVA-Studio-debug.apk"
}

package_ios() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "iOS packaging requires macOS with Xcode." >&2
    exit 1
  fi

  prepare_platform ios
  local derived_data="${ROOT_DIR}/artifacts/ios-derived"
  local app_path="${derived_data}/Build/Products/Release-iphoneos/App.app"
  local staging_dir="${ROOT_DIR}/artifacts/ios-package"

  rm -rf "${derived_data}" "${staging_dir}"
  xcodebuild \
    -project "${ROOT_DIR}/ios/App/App.xcodeproj" \
    -scheme App \
    -configuration Release \
    -destination "generic/platform=iOS" \
    -derivedDataPath "${derived_data}" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    build

  mkdir -p "${ARTIFACT_DIR}" "${staging_dir}/Payload"
  cp -R "${app_path}" "${staging_dir}/Payload/NOVA Studio.app"
  (
    cd "${staging_dir}"
    zip -qry "${ARTIFACT_DIR}/NOVA-Studio-unsigned.ipa" Payload
  )
}

case "${PLATFORM}" in
  android)
    package_android
    ;;
  ios)
    package_ios
    ;;
  *)
    echo "Usage: $0 android|ios" >&2
    exit 2
    ;;
esac
