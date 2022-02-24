#!/bin/bash

set -eu

if [[ $(uname -s) == Darwin ]]; then
  readonly MYDIR=$(cd "$(dirname "$(greadlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
else
  readonly MYDIR=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
fi

AQM_DIR="${MYDIR}"
SRW_APP_DIR="${AQM_DIR}/.."
SRC_DIR="${SRW_APP_DIR}/src/AQM-utils/gefs2clbcs_para"
BUILD_DIR="${SRW_APP_DIR}/build"
BIN_DIR="${SRW_APP_DIR}/bin"
MOD_DIR="${SRW_APP_DIR}/env"

# Detect MACHINE
source ${SRW_APP_DIR}/env/detect_machine.sh

###########################################################################
## User specific parameters                                              ##
###########################################################################
##
COMPILER="${COMPILER:-intel}"
##
###########################################################################

echo "MACHINE:" ${MACHINE}
echo "COMPILER:" ${COMPILER}

MOD_FILE="${MOD_DIR}/build_aqm_${PLATFORM}_${COMPILER}"

# Load modules
#module purge
#module use ${MOD_DIR}
#source ${MOD_FILE}
#module list

mkdir -p ${BUILD_DIR}
mkdir -p ${BIN_DIR}

cp -r "${SRC_DIR}" "${BUILD_DIR}/"

cd "${BUILD_DIR}/gefs2clbcs_para"

mkdir -p ${BIN_DIR}

make

cp "${BUILD_DIR}/gefs2clbcs_para/gefs2lbc_para" "${BIN_DIR}/gefs2lbc_para"

echo "gefs2lbc_para has been copied to bin (exec)."

