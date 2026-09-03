#!/usr/bin/env bash
# Build the aarch64 archive installable on the Remote (requires Docker with arm64 emulation).
set -euo pipefail

IMAGE="docker.io/unfoldedcircle/r2-pyinstaller:3.11.12-0.3.0"
DRIVER_ID="$(jq -r .driver_id driver.json)"
VERSION="$(jq -r .version driver.json)"
APP_NAME="intg-${DRIVER_ID}"
ARCHIVE_NAME="uc-${APP_NAME}-${VERSION}-aarch64.tar.gz"

SOURCE_DIR="$(pwd)"
BUILD_ROOT="/tmp/${APP_NAME}-build"
BUILD_DIR="${BUILD_ROOT}/repo"

rm -rf "${BUILD_ROOT}" "${SOURCE_DIR}/${ARCHIVE_NAME}"
mkdir -p "${BUILD_ROOT}"
rsync -a --exclude ".git/" --exclude "__pycache__/" --exclude "config/" \
  --exclude "dist/" --exclude "build/" --exclude "artifacts/" --exclude "*.tar.gz" \
  "${SOURCE_DIR}/" "${BUILD_DIR}/"

docker run --rm --platform=linux/arm64 --user="$(id -u):$(id -g)" \
  -v "${BUILD_DIR}:/workspace" "${IMAGE}" \
  bash -c "cd /workspace && python -m pip install -r requirements.txt && \
           pyinstaller --clean --onedir --name ${APP_NAME} intg-denon/driver.py"

mkdir -p "${BUILD_DIR}/artifacts/bin"
mv "${BUILD_DIR}/dist/${APP_NAME}/"* "${BUILD_DIR}/artifacts/bin/"
mv "${BUILD_DIR}/artifacts/bin/${APP_NAME}" "${BUILD_DIR}/artifacts/bin/driver"
cp "${BUILD_DIR}/driver.json" "${BUILD_DIR}/denon.png" "${BUILD_DIR}/artifacts/"

tar czf "${SOURCE_DIR}/${ARCHIVE_NAME}" -C "${BUILD_DIR}/artifacts" .
rm -rf "${BUILD_ROOT}"
echo "Built: ${ARCHIVE_NAME}"
