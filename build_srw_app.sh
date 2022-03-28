#!/bin/bash

###########################################################################
## Script to build UFS Short-Range Weather Application (UFS SRW App)     ##
##                                                                       ##
## Usage:                                                                ##
##  1. Non-coupled (FV3 stand-alone) regional modeling:                  ##
##             ./build_srw_app.sh                                        ##
##        or   ./build_srw_app.sh "FV3"                                  ##
##                                                                       ##
##  2. Coupled regional air quality modeling (RRFS-CMAQ):                ##
##             ./build_srw_app.sh "AQM"                                  ##
##                                                                       ##
###########################################################################

set -eu

if [[ $(uname -s) == Darwin ]]; then
  readonly MYDIR=$(cd "$(dirname "$(greadlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
else
  readonly MYDIR=$(cd "$(dirname "$(readlink -f -n "${BASH_SOURCE[0]}" )" )" && pwd -P)
fi

SRW_APP_DIR="${MYDIR}"
AQM_DIR="${SRW_APP_DIR}/AQM"
BUILD_DIR="${SRW_APP_DIR}/build"
BIN_DIR="${SRW_APP_DIR}/bin"
LIB_DIR="${SRW_APP_DIR}/lib"
MOD_DIR="${SRW_APP_DIR}/env"
SRC_DIR="${SRW_APP_DIR}/src"

###########################################################################
## User specific parameters                                              ##
###########################################################################
##
## Forecast model options ("FV3" or "AQM")
##    FV3  : FV3 stand-alone
##    AQM  : FV3 + AQM
##
FCST_opt="${1:-FV3}"
## 
## CCPP Suites: 
## For use of the default list (src/CMakeLists.txt): CCPP_SUITES=""
##
if [ ${FCST_opt} = "AQM" ]; then
  CCPP_SUITES="FV3_GFS_v15p2,FV3_GFS_v16"
else
  CCPP_SUITES=""
fi
##
## Compiler
##
export COMPILER="intel"
##
## Clean option ("YES" or else)
##    YES : clean build-related directories (bin,build,include,lib,share)
##
clean_opt="YES"
##
## Clone components ("YES" or else)
##
clone_externals="YES"
##
###########################################################################

echo "Forecast model option     :" ${FCST_opt}
if [ ! -z "${CCPP_SUITES}" ]; then
  echo "CCPP_SUITES               :" ${CCPP_SUITES}
else
  echo "CCPP_SUITES               : Default"
fi

if [ "${clone_externals}" = "YES" ]; then
  clean_opt="YES"
fi

echo "Clean option              :" ${clean_opt}
echo "Compiler                  :" ${COMPILER}
echo "Clone external components :" ${clone_externals}

if [ "${clean_opt}" = "YES" ]; then
  rm -rf ${BIN_DIR}
  rm -rf ${BUILD_DIR}
  rm -rf ${SRW_APP_DIR}/include
  rm -rf ${LIB_DIR}
  rm -rf ${SRW_APP_DIR}/share
fi

# detect PLATFORM (MACHINE)
source ${MOD_DIR}/detect_machine.sh

# Check out the external components
if [ "${clone_externals}" = "YES" ]; then
  echo "... Checking out the external components ..."
  if [ "${FCST_opt}" = "FV3" ]; then
    ./manage_externals/checkout_externals
  elif [ "${FCST_opt}" = "AQM" ]; then
    ./manage_externals/checkout_externals -e ${AQM_DIR}/Externals.cfg
  else
    echo "Fatal Error: forecast model is not on the list."
    exit 1
  fi
fi

# CMAKE settings
CMAKE_SETTINGS="-DCMAKE_INSTALL_PREFIX=${SRW_APP_DIR}"
if [ "${FCST_opt}" = "AQM" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DAPP=ATMAQ -DCPL_AQM=ON"
fi
if [ ! -z "${CCPP_SUITES}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DCCPP_SUITES=${CCPP_SUITES}"
fi

# Make build directory
mkdir -p ${BUILD_DIR}
cd ${BUILD_DIR}

##### Build UFS SRW App ##################################################
echo "... Load environment file ..."
MOD_FILE="${MOD_DIR}/build_${PLATFORM}_${COMPILER}.env"
module use ${MOD_DIR}
. ${MOD_FILE}
module list

echo "... Generate CMAKE configuration ..."
cmake ${SRW_APP_DIR} ${CMAKE_SETTINGS} 2>&1 | tee log.cmake.app
echo "... Compile executables ..."
make -j8 2>&1 | tee log.make.app
echo "... App build completed ..."

##### Build extra components for AQM #####################################
if [ "${FCST_opt}" = "AQM" ]; then
  cd ${AQM_DIR}
  ## GEFS2CLBC
  echo "... Build gefs2clbc-para ..."
  ./build_gefs2clbc.sh || exit 1

  ## Replace UPP control file
  echo "... Replace UPP control file ..."
  cp "${SRC_DIR}/AQM-utils/parm/postxconfig-NT-fv3lam_cmaq.txt" "${SRC_DIR}/UPP/parm/" || exit 1
fi

echo "===== App installed successfully !!! ====="

exit 0
