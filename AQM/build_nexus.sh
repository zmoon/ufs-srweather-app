#!/bin/bash

set -eu

if [[ $(uname -s) == Darwin ]]; then
  readonly MYDIR=$(cd "$(dirname "$(greadlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
else
  readonly MYDIR=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
fi

AQM_DIR="${MYDIR}"
SRW_APP_DIR="${AQM_DIR}/.."
SRC_DIR="${SRW_APP_DIR}/src/arl_nexus"
BUILD_DIR="${SRW_APP_DIR}/build/arl_nexus"
BIN_DIR="${SRW_APP_DIR}/bin"
MOD_DIR="${SRW_APP_DIR}/env"

# Detect MACHINE
source ${SRW_APP_DIR}/env/detect_machine.sh

###########################################################################
## User specific parameters                                              ##
###########################################################################
##
export COMPILER="${COMPILER:-intel}"
##
###########################################################################

echo "MACHINE:" ${MACHINE}
echo "COMPILER:" ${COMPILER}

MOD_FILE="${MOD_DIR}/build_aqm_${PLATFORM}_${COMPILER}.env"

# Load modules
#module purge
#module use ${MOD_DIR}
#module load ${MOD_FILE}
#module list

mkdir -p ${BUILD_DIR}
mkdir -p ${BIN_DIR}

cd ${BUILD_DIR}

CMAKE_SETTINGS="-DCMAKE_INSTALL_PREFIX=${SRC_DIR}"
#CMAKE_SETTINGS="${CMAKE_SETTINGS} -DEMC_EXEC_DIR=ON"

cmake -DCMAKE_INSTALL_PREFIX=${SRW_APP_DIR} ${SRC_DIR} 2>&1 | tee log.cmake.nexus
make -j4 2>&1 | tee log.make.nexus
make install

echo "arl_nexus has been copied to bin (exec)."
