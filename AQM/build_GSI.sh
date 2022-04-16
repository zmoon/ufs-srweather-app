#!/bin/bash

set -eu

if [[ $(uname -s) == Darwin ]]; then
  readonly MYDIR=$(cd "$(dirname "$(greadlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
else
  readonly MYDIR=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
fi

SRW_APP_DIR="${MYDIR}/.."
SRC_DIR="${SRW_APP_DIR}/src/gsi"
BUILD_DIR="${SRW_APP_DIR}/build/gsi"
BIN_DIR="${SRW_APP_DIR}/bin/"

cp -r ${SRC_DIR} ${BUILD_DIR}
mkdir -p ${BIN_DIR}

cd ${BUILD_DIR}

./ush/build.comgsi

cp "${BUILD_DIR}/build/bin/gsi.x" ${BIN_DIR}

echo "The executable gsi.x has been copied to bin"
