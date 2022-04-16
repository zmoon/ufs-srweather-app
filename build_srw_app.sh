#!/bin/bash

###########################################################################
##                                                                       ##
## Script to build UFS Short-Range Weather Application (UFS SRW App)     ##
##                                                                       ##
## Usage (basic examples):                                               ##
##  1. Non-coupled (ATM stand-alone) regional modeling:                  ##
##          ./build_srw_app.sh                                           ##
##       or ./build_srw_app.sh --app=ATM                                 ##
##                                                                       ##
##  2. Coupled regional air quality modeling (RRFS-CMAQ=ATM+AQM):        ##
##          ./build_srw_app.sh --app=AQM  --da=YES                       ##
##                                                                       ##
###########################################################################

## Usage setting ==========================================================
usage () {
cat << EOF_USAGE
Usage: $0 [OPTIONS]...
OPTIONS
  -h, --help
      show this help guide
  --app=APPLICATION
      SRW App application to build
      (ATM: non-coupled ATM stand-alone | AQM: ATM+AQM)
  --platform=PLATFORM
      name of machine you are building on
      (e.g. hera | orion | wcoss_dell_p3)
  --compiler=COMPILER
      compiler to use; default depends on platform
      (e.g. intel | gnu )
  --ccpp="CCPP_SUITE1,CCPP_SUITE2..."
      CCCP suites to include in build; delimited with ','
  --extrn=EXTERNALS
      Check out external components (YES or NO)
  --da=DA
      build DA components: GSI and JEDI (YES or NO)
EOF_USAGE
}

# Print out usage error and exit
usage_error () {
  printf "ERROR: $1\n" >&2
  usage >&2
  exit 1
}

# Print out usage options
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  usage
  exit 0
fi

## Default settings =======================================================
APPLICATION="ATM"
PLATFORM="hera"
COMPILER="intel"
CCPP_SUITES=""
EXTERNALS="YES"
DA="NO"

## Update of optional arguments ===========================================
while :; do
  case $1 in
    --help|-h) usage; exit 0 ;;
    --app=?*) APPLICATION=${1#*=} ;;
    --app|--app=) usage_error "$1 requires argument." ;;
    --platform=?*) PLATFORM=${1#*=} ;;
    --platform|--platform=) usage_error "$1 requires argument." ;;
    --compiler=?*) COMPILER=${1#*=} ;;
    --compiler|--compiler=) usage_error "$1 requires argument." ;;
    --ccpp=?*) CCPP_SUITES=${1#*=} ;;
    --ccpp|--ccpp=) usage_error "$1 requires argument." ;;
    --extrn=?*) EXTERNALS=${1#*=} ;;
    --extrn|--extrn=) usage_error "$1 requires argument." ;;
    --da=?*) DA=${1#*=} ;;
    --da|--da=) usage_error "$1 requires argument." ;;
    -?*|?*) usage_error "Unknown option $1" ;;
    *) break
  esac
  shift
done

## Ensure uppercase / lowercase ===========================================
APPLICATION="${APPLICATION^^}"
PLATFORM="${PLATFORM,,}"
COMPILER="${COMPILER,,}"
EXTERNALS="${EXTERNALS^^}"
DA="${DA^^}"

## Ensure platform name from variance =====================================
if [[ "${PLATFORM}" == "wcoss_dell" || "${PLATFORM}" == "wcoss1" ||
      "${PLATFORM}" == "venus" || "${PLATFORM}" = "mars" ||
      "${PLATFORM}" == "wcoss_dell_p35" ]]; then
  PLATFORM="wcoss_dell_p3"
fi

## Print out parameter values =============================================
echo "Application        :" ${APPLICATION}
echo "Platform (machine) :" ${PLATFORM}
echo "Compiler           :" ${COMPILER}
if [ ! -z "${CCPP_SUITES}" ]; then
  echo "CCPP_SUITES        :" ${CCPP_SUITES}
else
  echo "CCPP_SUITES        : Default in src/CMakeLists.txt"
fi
echo "External checkout  :" ${EXTERNALS}
echo "DA components      :" ${DA}


##########
set -eu
##########

## Directories ============================================================
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

## Output file name to check executables in BIN_DIR =======================
BUILD_OUT_FN="build_exec_pass.out"


### List of Excutables ### ================================================
## Basic executables of the UFS SRW App ===================================
declare -a exec_srw=( chgres_cube \
                      emcsfc_ice_blend \
                      emcsfc_snow2mdl \
                      filter_topo \
                      fregrid \
                      fvcom_to_FV3 \
                      global_cycle \
                      global_equiv_resol \
                      inland \
                      lakefrac \
                      make_hgrid \
                      make_solo_mosaic \
                      orog \
                      orog_gsl \
                      regional_esg_grid \
                      sfc_climo_gen \
                      shave \
                      ufs_model \
                      upp.x \
                      vcoord_gen )
## Additional executables for AQM =========================================
declare -a exec_aqm=( nexus \
                      gefs2lbc_para )

## Additional executables for DA ==========================================
declare -a exec_da=( gsi.x \
                     fv3jedi_addincrement.x \
                     fv3jedi_adjointforecast.x \
                     fv3jedi_convertincrement.x \
                     fv3jedi_convertstate.x \
                     fv3jedi_data_checker.x \
                     fv3jedi_diffstates.x \
                     fv3jedi_dirac.x \
                     fv3jedi_eda.x \
                     fv3jedi_enshofx.x \
                     fv3jedi_ensvariance.x \
                     fv3jedi_error_covariance_training.x \
                     fv3jedi_forecast.x \
                     fv3jedi_hofx.x \
                     fv3jedi_hofx_nomodel.x \
                     fv3jedi_letkf.x \
                     fv3jedi_plot_field.x \
                     fv3jedi_testdata_downloader.py \
                     fv3jedi_var.x )

## Remove build-related directories when EXTERNALS=YES ====================
if [ "${EXTERNALS}" = "YES" ]; then
  rm -rf ${BIN_DIR}
  rm -rf ${BUILD_DIR}
  rm -rf ${SRW_APP_DIR}/include
  rm -rf ${LIB_DIR}
  rm -rf ${SRW_APP_DIR}/share
  rm -f ${BUILD_OUT_FN}
fi

## Check out external components ==========================================
if [ "${EXTERNALS}" = "YES" ]; then
  echo "... Checking out the external components ..."
  if [ "${APPLICATION}" = "ATM" ]; then
    ./manage_externals/checkout_externals
  elif [ "${APPLICATION}" = "AQM" ]; then
    if [ "${DA}" = "YES" ]; then
      ./manage_externals/checkout_externals -e ${AQM_DIR}/Externals_DA.cfg
    else
      ./manage_externals/checkout_externals -e ${AQM_DIR}/Externals.cfg
    fi
  else
    echo "Fatal Error: application is not on the list."
    exit 1
  fi
fi

## CMAKE settings =========================================================
CMAKE_SETTINGS="-DCMAKE_INSTALL_PREFIX=${SRW_APP_DIR}"
if [ "${APPLICATION}" = "AQM" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DAPP=ATMAQ -DCPL_AQM=ON"
fi
if [ ! -z "${CCPP_SUITES}" ]; then
  CMAKE_SETTINGS="${CMAKE_SETTINGS} -DCCPP_SUITES=${CCPP_SUITES}"
fi

## Make build directory ===================================================
mkdir -p ${BUILD_DIR}
cd ${BUILD_DIR}

## Build UFS SRW App ======================================================
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

## Build DA components: GSI and JEDI ======================================
if [ "${DA}" = "YES" ]; then
  echo "... Building GSI ..."
  cd ${AQM_DIR}
  ./build_GSI.sh
  echo "... Building JEDI ..."
  ./build_JEDI.sh
fi


cd ${SRW_APP_DIR}

## Create output file to check if executables exist in BIN_DIR ============
if [ ! -f "${BUILD_OUT_FN}" ]; then
   touch ${BUILD_OUT_FN}
fi

## Check if all executables exist in BIN_DIR ==============================
n_fail=0
echo $( date --utc ) >> ${BUILD_OUT_FN}
for file in "${exec_srw[@]}" ; do
  exec_file="${BIN_DIR}/${file}"
  if [ -f ${exec_file} ]; then
    echo "PASS:: executable = ${file}" >> ${BUILD_OUT_FN}
  else
    echo "FAIL:: executable = ${file}" >> ${BUILD_OUT_FN}
    (( n_fail=n_fail+1 ))
  fi
done
if [ "${APPLICATION}" = "AQM" ]; then
  for file in "${exec_aqm[@]}" ; do
    exec_file="${BIN_DIR}/${file}"
    if [ -f ${exec_file} ]; then
      echo "PASS:: executable = ${file}" >> ${BUILD_OUT_FN}
    else
      echo "FAIL:: executable = ${file}" >> ${BUILD_OUT_FN}
      (( n_fail=n_fail+1 ))
    fi
  done
fi
if [ "${DA}" = "YES" ]; then
  for file in "${exec_da[@]}" ; do
    exec_file="${BIN_DIR}/${file}"
    if [ -f ${exec_file} ]; then
      echo "PASS:: executable = ${file}" >> ${BUILD_OUT_FN}
    else
      echo "FAIL:: executable = ${file}" >> ${BUILD_OUT_FN}
      (( n_fail=n_fail+1 ))
    fi
  done
fi

if [ ${n_fail} -eq 0 ]; then
  echo "===== App-build: COMPLETED !!! ====="
else
  echo "===== App-build: FAILED !!! ====="
  echo "===== Number of failed executables:" ${n_fail}
  echo "===== Please check:" ${BUILD_OUT_FN}
fi

exit 0
